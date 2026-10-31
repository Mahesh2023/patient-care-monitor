"""FastAPI dependencies: auth, rate limiting, ownership checks."""
from __future__ import annotations

import time
import uuid
from typing import Annotated
from collections.abc import Callable

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from src.care_monitor.config import settings

from .core.db import get_db
from .core.kv import kv
from .core.security import TokenError, decode_token
from .models import Patient, User

DB = Annotated[AsyncSession, Depends(get_db)]
_bearer = HTTPBearer(auto_error=False)


def client_ip(request: Request) -> str:
    # uvicorn --proxy-headers rewrites client.host from X-Forwarded-For.
    return request.client.host if request.client else "unknown"


def rate_limit(scope: str, per_minute_attr: str) -> Callable:
    async def _dep(request: Request) -> None:
        limit = int(getattr(settings, per_minute_attr))
        if limit <= 0:
            return
        window = int(time.time() // 60)
        n = await kv.incr_window(f"rl:{scope}:{client_ip(request)}:{window}", 60)
        if n > limit:
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "rate limit exceeded",
                                headers={"Retry-After": str(60 - int(time.time()) % 60)})
    return _dep


async def current_user(
    db: DB,
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> User:
    unauthorized = HTTPException(status.HTTP_401_UNAUTHORIZED, "not authenticated",
                                 headers={"WWW-Authenticate": "Bearer"})
    if creds is None:
        raise unauthorized
    try:
        claims = decode_token(creds.credentials, "access")
        uid = uuid.UUID(claims["sub"])
    except (TokenError, ValueError):
        raise unauthorized from None
    user = await db.get(User, uid)
    if user is None or not user.is_active or user.token_version != claims.get("ver"):
        raise unauthorized
    return user


CurrentUser = Annotated[User, Depends(current_user)]


async def owned_patient(db: AsyncSession, user: User, patient_id: uuid.UUID) -> Patient:
    p = await db.get(Patient, patient_id)
    if p is None or p.owner_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "patient not found")
    return p
