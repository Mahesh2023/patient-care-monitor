"""Authentication: register / login / refresh (rotating) / logout / me."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, UTC

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from src.care_monitor.config import settings

from ..core.security import (
    TokenError, create_access_token, create_refresh_token, decode_token, hash_password,
    verify_password,
)
from ..deps import DB, CurrentUser, rate_limit
from ..models import RefreshToken, User, utcnow
from ..schemas import LoginIn, PasswordChangeIn, RegisterIn, TokenOut, UserOut

router = APIRouter(prefix="/api/auth", tags=["auth"])
COOKIE = "care_rt"
COOKIE_PATH = "/api/auth"
_auth_rl = Depends(rate_limit("auth", "auth_rate_per_minute"))


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


@router.post("/register", response_model=TokenOut, status_code=201, dependencies=[_auth_rl])
async def register(body: RegisterIn, response: Response, db: DB) -> TokenOut:
    user = User(email=body.email.lower(), password_hash=await hash_password(body.password),
                full_name=body.full_name.strip())
    db.add(user)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "email already registered") from None
    return await _issue(db, user, response)


@router.post("/login", response_model=TokenOut, dependencies=[_auth_rl])
async def login(body: LoginIn, response: Response, db: DB) -> TokenOut:
    user = (await db.execute(select(User).where(User.email == body.email.lower()))).scalar_one_or_none()
    ok = await verify_password(body.password, user.password_hash if user else None)
    if not ok or user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid credentials")
    return await _issue(db, user, response)


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
    if raw:
        try:
            claims = decode_token(raw, "refresh")
            await db.execute(update(RefreshToken).where(RefreshToken.id == uuid.UUID(claims["jti"]))
                             .values(revoked_at=utcnow()))
            await db.commit()
        except (TokenError, KeyError, ValueError):
            pass
    response.status_code = 204
    response.delete_cookie(COOKIE, path=COOKIE_PATH)
    return response


@router.get("/me", response_model=UserOut)
async def me(user: CurrentUser) -> User:
    return user


@router.post("/password", status_code=204, dependencies=[_auth_rl])
async def change_password(body: PasswordChangeIn, user: CurrentUser, db: DB, response: Response) -> Response:
    if not await verify_password(body.current_password, user.password_hash):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "current password incorrect")
    user.password_hash = await hash_password(body.new_password)
    user.token_version += 1  # invalidates all access tokens
    await db.execute(update(RefreshToken).where(RefreshToken.user_id == user.id,
                                                RefreshToken.revoked_at.is_(None))
                     .values(revoked_at=datetime.now(UTC)))
    await db.commit()
    response.status_code = 204
    response.delete_cookie(COOKIE, path=COOKIE_PATH)
    return response


@router.delete("/me", status_code=204)
async def delete_account(user: CurrentUser, db: DB, response: Response) -> Response:
    """GDPR Art. 17: erase the account and (via FK cascade) all patient data."""
    await db.delete(user)
    await db.commit()
    response.status_code = 204
    response.delete_cookie(COOKIE, path=COOKIE_PATH)
    return response
