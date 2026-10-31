"""Audit trail helper (HIPAA §164.312(b): record and examine activity on ePHI).

Records who did what to which patient/resource, when, from where (HMAC'd
IP), with the request id for log correlation. Written in its own short
transaction so a failure in the business transaction is still audited and
an audit failure never breaks the request (logged instead).
"""
from __future__ import annotations

import uuid
from typing import Any, Optional

from fastapi import Request

from src.care_monitor.logging_utils import get_logger, request_id_var
from src.care_monitor.privacy import hash_ip

from .db import SessionLocal

log = get_logger(__name__)


async def audit(action: str, request: Optional[Request] = None, *,
                user_id: Optional[uuid.UUID] = None,
                patient_id: Optional[uuid.UUID] = None,
                resource_type: Optional[str] = None,
                resource_id: Any = None,
                success: bool = True,
                detail: Optional[dict[str, Any]] = None,
                ip: Optional[str] = None) -> None:
    from ..models import AuditEvent  # local import avoids a cycle with models -> db
    if ip is None and request is not None and request.client:
        ip = request.client.host
    try:
        async with SessionLocal() as db:
            db.add(AuditEvent(
                user_id=user_id, action=action[:48], patient_id=patient_id,
                resource_type=resource_type, resource_id=str(resource_id)[:64] if resource_id else None,
                success=success, ip_hash=hash_ip(ip), request_id=request_id_var.get()[:64],
                detail=detail,
            ))
            await db.commit()
    except Exception as e:  # never let auditing break the request path
        log.error("audit write failed (%s): %s", action, e)
