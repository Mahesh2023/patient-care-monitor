"""Password hashing (argon2id) and JWT issuing / verification.

Token types (the `typ` claim is always checked to prevent token confusion):
  access   15 min, Bearer header, carries `ver` (user.token_version) so a
           password change / logout-all invalidates every outstanding token.
  refresh  30 days, httpOnly+Secure+SameSite=Strict cookie scoped to
           /api/auth, rotated on every use, revocable server-side (jti row).
  ws       60 s, single-purpose ticket bound to one monitoring session; used
           as a WS query param because browsers cannot set WS headers.
"""
from __future__ import annotations

import time
import uuid
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from starlette.concurrency import run_in_threadpool

from src.care_monitor.config import settings

# OWASP 2023 minimum argon2id profile (19 MiB, t=2, p=1): safe on 512 MB hosts.
_ph = PasswordHasher(time_cost=2, memory_cost=19456, parallelism=1)
_DUMMY_HASH = _ph.hash("timing-equaliser")
ISSUER = "care-mm"


async def hash_password(password: str) -> str:
    return await run_in_threadpool(_ph.hash, password)


async def verify_password(password: str, hashed: str | None) -> bool:
    """Constant-ish time: always runs one argon2 verify, even for unknown users."""
    def _verify() -> bool:
        try:
            return _ph.verify(hashed or _DUMMY_HASH, password) and hashed is not None
        except (VerificationError, InvalidHashError):
            return False
    return await run_in_threadpool(_verify)


class TokenError(Exception):
    pass


def _encode(claims: dict[str, Any], ttl_s: int) -> str:
    now = int(time.time())
    payload = {"iss": ISSUER, "iat": now, "exp": now + ttl_s, **claims}
    return jwt.encode(payload, settings.effective_jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str, typ: str) -> dict[str, Any]:
    try:
        claims = jwt.decode(
            token, settings.effective_jwt_secret, algorithms=[settings.jwt_algorithm],
            issuer=ISSUER, options={"require": ["exp", "iat", "sub", "typ"]},
        )
    except jwt.PyJWTError as e:
        raise TokenError(str(e)) from e
    if claims.get("typ") != typ:
        raise TokenError("wrong token type")
    return claims


def create_access_token(user_id: uuid.UUID, token_version: int) -> str:
    return _encode({"sub": str(user_id), "typ": "access", "ver": token_version},
                   settings.jwt_access_ttl_minutes * 60)


def create_refresh_token(user_id: uuid.UUID, jti: uuid.UUID) -> str:
    return _encode({"sub": str(user_id), "typ": "refresh", "jti": str(jti)},
                   settings.jwt_refresh_ttl_days * 86400)


def create_ws_ticket(user_id: uuid.UUID, session_id: uuid.UUID, purpose: str = "ingest") -> str:
    return _encode({"sub": str(user_id), "typ": "ws", "sid": str(session_id), "pur": purpose},
                   settings.ws_ticket_ttl_seconds)
