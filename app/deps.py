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
from .models import Patient, PatientMember, User

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


# Care-team roles (least privilege):
#   viewer  read patient data, live alert watch
#   editor  + start monitoring, acknowledge alerts, PAINAD assessments, care events
#   owner   + edit/delete patient, alert settings, team management, export, access log
ROLE_RANK = {"viewer": 1, "editor": 2, "owner": 3}


async def role_for(db: AsyncSession, user_id: uuid.UUID, patient: Patient) -> str | None:
    if patient.owner_id == user_id:
        return "owner"
    m = await db.get(PatientMember, (patient.id, user_id))
    return m.role if m else None


async def patient_access(db: AsyncSession, user: User, patient_id: uuid.UUID,
                         min_role: str = "viewer") -> tuple[Patient, str]:
    """Return (patient, role) or 404 (no access) / 403 (insufficient role).

    404 for no access at all avoids disclosing that a patient id exists.
    """
    p = await db.get(Patient, patient_id)
    role = await role_for(db, user.id, p) if p else None
    if role is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "patient not found")
    if ROLE_RANK[role] < ROLE_RANK[min_role]:
        raise HTTPException(status.HTTP_403_FORBIDDEN, f"requires {min_role} role")
    return p, role


async def owned_patient(db: AsyncSession, user: User, patient_id: uuid.UUID) -> Patient:
    return (await patient_access(db, user, patient_id, "owner"))[0]
