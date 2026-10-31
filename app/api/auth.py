"""Authentication: register / login (+TOTP 2FA) / refresh (rotating) / logout / me.

Defences (OWASP ASVS 5.0 V6, NIST SP 800-63B):
  * argon2id hashing, constant-time verify for unknown accounts;
  * common / context / breached password rejection (app.core.passwords);
  * per-IP rate limit + per-account soft lockout (counter in shared KV,
    applied to unknown emails too so it cannot be used for enumeration);
  * optional TOTP second factor with replay protection and one-time
    recovery codes; MFA step uses a 5-minute single-purpose token;
  * every security-relevant event is written to the audit trail.
"""
from __future__ import annotations

import hashlib
import time
import uuid
from datetime import timedelta
from typing import Union

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from src.care_monitor.config import settings

from ..core import totp
from ..core.audit import audit
from ..core.kv import kv
from ..core.passwords import WeakPassword, validate_password
from ..core.security import (
    TokenError, _encode, create_access_token, create_refresh_token, decode_token, hash_password,
    verify_password,
)
from ..deps import DB, CurrentUser, rate_limit
from ..models import AuditEvent, RefreshToken, User, utcnow
from ..schemas import (
    AuditOut, LoginIn, MfaChallengeOut, MfaVerifyIn, PasswordChangeIn, RecoveryCodesOut, RegisterIn,
    TokenOut, TotpCodeIn, TotpDisableIn, TotpSetupOut, UserOut,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])
COOKIE = "care_rt"
COOKIE_PATH = "/api/auth"
_auth_rl = Depends(rate_limit("auth", "auth_rate_per_minute"))


def _lock_key(email: str) -> str:
    return "lf:" + hashlib.sha256(email.lower().encode()).hexdigest()[:32]


async def _check_lockout(email: str, request: Request) -> None:
    if await kv.get_int(_lock_key(email)) >= settings.login_max_failures:
        await audit("auth.lockout", request, success=False, detail={"email_hash": _lock_key(email)[3:]})
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS,
                            "too many failed attempts — try again later",
                            headers={"Retry-After": str(settings.login_lockout_seconds)})


async def _record_failure(email: str) -> None:
    await kv.incr(_lock_key(email), 1, settings.login_lockout_seconds)


async def _issue(db: DB, user: User, response: Response) -> TokenOut:
    jti = uuid.uuid4()
    db.add(RefreshToken(id=jti, user_id=user.id,
                        expires_at=utcnow() + timedelta(days=settings.jwt_refresh_ttl_days)))
    await db.commit()
    response.set_cookie(
        COOKIE, create_refresh_token(user.id, jti),
        max_age=settings.jwt_refresh_ttl_days * 86400, httponly=True,
        secure=settings.cookie_secure, samesite="strict", path=COOKIE_PATH,
    )
    return TokenOut(access_token=create_access_token(user.id, user.token_version),
                    expires_in=settings.jwt_access_ttl_minutes * 60)


def _weak(e: WeakPassword) -> HTTPException:
    return HTTPException(422, str(e))


@router.post("/register", response_model=TokenOut, status_code=201, dependencies=[_auth_rl])
async def register(body: RegisterIn, request: Request, response: Response, db: DB) -> TokenOut:
    email = body.email.lower()
    try:
        await validate_password(body.password, email)
    except WeakPassword as e:
        raise _weak(e) from None
    user = User(email=email, password_hash=await hash_password(body.password), full_name=body.full_name.strip())
    db.add(user)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "email already registered") from None
    out = await _issue(db, user, response)
    await audit("auth.register", request, user_id=user.id)
    return out


@router.post("/login", response_model=Union[TokenOut, MfaChallengeOut], dependencies=[_auth_rl])  # noqa: UP007
async def login(body: LoginIn, request: Request, response: Response, db: DB):
    email = body.email.lower()
    await _check_lockout(email, request)
    user = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
    ok = await verify_password(body.password, user.password_hash if user else None)
    if not ok or user is None or not user.is_active:
        await _record_failure(email)
        await audit("auth.login", request, user_id=user.id if user else None, success=False)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid credentials")
    if user.totp_enabled:
        token = _encode({"sub": str(user.id), "typ": "mfa", "ver": user.token_version}, settings.mfa_token_ttl_seconds)
        await audit("auth.login.mfa_challenge", request, user_id=user.id)
        return MfaChallengeOut(mfa_token=token)
    await kv.delete(_lock_key(email))
    out = await _issue(db, user, response)
    await audit("auth.login", request, user_id=user.id)
    return out


async def _consume_second_factor(db: DB, user: User, code: str) -> str | None:
    """Verify TOTP (with replay protection) or a one-time recovery code. Returns method or None."""
    if user.totp_secret_enc:
        step = totp.verify(totp.decrypt(user.totp_secret_enc), code, user.totp_last_step)
        if step is not None:
            user.totp_last_step = step
            return "totp"
    digest = totp.hash_recovery(code)
    if user.recovery_codes and digest in user.recovery_codes:
        user.recovery_codes = [c for c in user.recovery_codes if c != digest]
        return "recovery_code"
    return None


@router.post("/2fa/verify", response_model=TokenOut, dependencies=[_auth_rl])
async def mfa_verify(body: MfaVerifyIn, request: Request, response: Response, db: DB) -> TokenOut:
    invalid = HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid or expired code")
    try:
        claims = decode_token(body.mfa_token, "mfa")
        user = await db.get(User, uuid.UUID(claims["sub"]))
    except (TokenError, KeyError, ValueError):
        raise invalid from None
    if user is None or not user.is_active or not user.totp_enabled or user.token_version != claims.get("ver"):
        raise invalid
    email, uid = user.email, user.id
    await _check_lockout(email, request)
    method = await _consume_second_factor(db, user, body.code)
    if method is None:
        await db.rollback()
        await _record_failure(email)
        await audit("auth.mfa", request, user_id=uid, success=False)
        raise invalid
    await kv.delete(_lock_key(email))
    out = await _issue(db, user, response)  # commits totp_last_step / consumed recovery code
    await audit("auth.mfa", request, user_id=uid, detail={"method": method})
    return out


@router.post("/refresh", response_model=TokenOut, dependencies=[_auth_rl])
async def refresh(request: Request, response: Response, db: DB) -> TokenOut:
    invalid = HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid refresh token")
    raw = request.cookies.get(COOKIE)
    if not raw:
        raise invalid
    try:
        claims = decode_token(raw, "refresh")
        jti, uid = uuid.UUID(claims["jti"]), uuid.UUID(claims["sub"])
    except (TokenError, KeyError, ValueError):
        raise invalid from None
    # Atomic single-use: only one concurrent refresh can flip revoked_at.
    res = await db.execute(
        update(RefreshToken)
        .where(RefreshToken.id == jti, RefreshToken.user_id == uid, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=utcnow())
    )
    if res.rowcount != 1:
        # Re-use of a rotated token => possible theft: revoke the whole family.
        await db.execute(update(RefreshToken).where(RefreshToken.user_id == uid,
                                                    RefreshToken.revoked_at.is_(None))
                         .values(revoked_at=utcnow()))
        await db.commit()
        await audit("auth.refresh_reuse_detected", request, user_id=uid, success=False)
        response.delete_cookie(COOKIE, path=COOKIE_PATH)
        raise invalid
    user = await db.get(User, uid)
    if user is None or not user.is_active:
        await db.commit()
        raise invalid
    return await _issue(db, user, response)


@router.post("/logout", status_code=204)
async def logout(request: Request, response: Response, db: DB) -> Response:
    raw = request.cookies.get(COOKIE)
    uid = None
    if raw:
        try:
            claims = decode_token(raw, "refresh")
            uid = uuid.UUID(claims["sub"])
            await db.execute(update(RefreshToken).where(RefreshToken.id == uuid.UUID(claims["jti"]))
                             .values(revoked_at=utcnow()))
            await db.commit()
        except (TokenError, KeyError, ValueError):
            pass
    if uid:
        await audit("auth.logout", request, user_id=uid)
    response.status_code = 204
    response.delete_cookie(COOKIE, path=COOKIE_PATH)
    return response


@router.get("/me", response_model=UserOut)
async def me(user: CurrentUser) -> User:
    return user


async def _revoke_all(db: DB, user: User) -> None:
    user.token_version += 1  # invalidates all access tokens
    await db.execute(update(RefreshToken).where(RefreshToken.user_id == user.id,
                                                RefreshToken.revoked_at.is_(None))
                     .values(revoked_at=utcnow()))


@router.post("/password", status_code=204, dependencies=[_auth_rl])
async def change_password(body: PasswordChangeIn, request: Request, user: CurrentUser, db: DB,
                          response: Response) -> Response:
    if not await verify_password(body.current_password, user.password_hash):
        await audit("auth.password_change", request, user_id=user.id, success=False)
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "current password incorrect")
    try:
        await validate_password(body.new_password, user.email)
    except WeakPassword as e:
        raise _weak(e) from None
    user.password_hash = await hash_password(body.new_password)
    await _revoke_all(db, user)
    await db.commit()
    await audit("auth.password_change", request, user_id=user.id)
    response.status_code = 204
    response.delete_cookie(COOKIE, path=COOKIE_PATH)
    return response


# ---- TOTP 2FA management --------------------------------------------
@router.post("/2fa/setup", response_model=TotpSetupOut, dependencies=[_auth_rl])
async def totp_setup(request: Request, user: CurrentUser, db: DB) -> TotpSetupOut:
    if user.totp_enabled:
        raise HTTPException(status.HTTP_409_CONFLICT, "two-factor authentication already enabled")
    secret = totp.generate_secret()
    user.totp_secret_enc, user.totp_last_step = totp.encrypt(secret), 0
    await db.commit()
    await audit("auth.2fa_setup", request, user_id=user.id)
    return TotpSetupOut(secret=secret, otpauth_uri=totp.provisioning_uri(secret, user.email))


@router.post("/2fa/enable", response_model=RecoveryCodesOut, dependencies=[_auth_rl])
async def totp_enable(body: TotpCodeIn, request: Request, user: CurrentUser, db: DB) -> RecoveryCodesOut:
    if user.totp_enabled or not user.totp_secret_enc:
        raise HTTPException(status.HTTP_409_CONFLICT, "run setup first")
    step = totp.verify(totp.decrypt(user.totp_secret_enc), body.code, user.totp_last_step)
    if step is None:
        await audit("auth.2fa_enable", request, user_id=user.id, success=False)
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid code")
    codes, digests = totp.new_recovery_codes()
    user.totp_enabled, user.totp_last_step, user.recovery_codes = True, step, digests
    await _revoke_all(db, user)  # other sessions must re-authenticate with the second factor
    await db.commit()
    await audit("auth.2fa_enable", request, user_id=user.id)
    return RecoveryCodesOut(recovery_codes=codes)


@router.post("/2fa/disable", status_code=204, dependencies=[_auth_rl])
async def totp_disable(body: TotpDisableIn, request: Request, user: CurrentUser, db: DB) -> Response:
    if not user.totp_enabled:
        raise HTTPException(status.HTTP_409_CONFLICT, "two-factor authentication is not enabled")
    uid = user.id
    if not await verify_password(body.password, user.password_hash) or \
            await _consume_second_factor(db, user, body.code) is None:
        await db.rollback()
        await audit("auth.2fa_disable", request, user_id=uid, success=False)
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid password or code")
    user.totp_enabled, user.totp_secret_enc, user.recovery_codes, user.totp_last_step = False, None, None, 0
    await db.commit()
    await audit("auth.2fa_disable", request, user_id=user.id)
    return Response(status_code=204)


@router.get("/audit", response_model=list[AuditOut])
async def my_audit(user: CurrentUser, db: DB, limit: int = 100) -> list[AuditEvent]:
    """The caller's own security / access history."""
    limit = max(1, min(limit, 500))
    q = select(AuditEvent).where(AuditEvent.user_id == user.id).order_by(AuditEvent.ts.desc()).limit(limit)
    return list((await db.execute(q)).scalars().all())


@router.delete("/me", status_code=204)
async def delete_account(request: Request, user: CurrentUser, db: DB, response: Response) -> Response:
    """GDPR Art. 17: erase the account and (via FK cascade) all owned patient data.

    The audit trail is retained (pseudonymous ids only) as required for
    security accountability.
    """
    uid = user.id
    await db.delete(user)
    await db.commit()
    await audit("auth.account_delete", request, user_id=uid, detail={"at": int(time.time())})
    response.status_code = 204
    response.delete_cookie(COOKIE, path=COOKIE_PATH)
    return response
