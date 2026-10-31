"""Monitoring sessions: consent-gated start, WS tickets, end, revoke; alert ack."""
from __future__ import annotations

import uuid
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, status

from src.care_monitor.config import settings
from src.care_monitor.privacy import hash_ip

from ..core.audit import audit
from ..core.security import create_ws_ticket
from ..deps import DB, CurrentUser, client_ip, patient_access, rate_limit, role_for
from ..models import Alert, MonitoringSession, Patient, User, utcnow
from ..schemas import AlertOut, SessionOut, SessionStartIn, SessionStartOut, TicketOut

router = APIRouter(prefix="/api", tags=["sessions"],
                   dependencies=[Depends(rate_limit("api", "api_rate_per_minute"))])


async def _session_for(db: DB, user: User, session_id: uuid.UUID, allow_owner: bool = False) -> MonitoringSession:
    """The caregiver who started a session controls it; the patient owner may also end/revoke."""
    s = await db.get(MonitoringSession, session_id)
    if s is not None and s.user_id != user.id and allow_owner:
        p = await db.get(Patient, s.patient_id)
        if p is not None and p.owner_id == user.id:
            return s
    if s is None or s.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "session not found")
    return s


@router.post("/sessions", response_model=SessionStartOut, status_code=201)
async def start_session(body: SessionStartIn, request: Request, user: CurrentUser, db: DB):
    if not body.consent_confirmed:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "informed consent must be confirmed")
    patient, _ = await patient_access(db, user, body.patient_id, "editor")
    now = utcnow()
    s = MonitoringSession(
        patient_id=patient.id, user_id=user.id, consent_purpose=body.purpose,
        consent_granted_at=now, consent_expires_at=now + timedelta(hours=settings.consent_ttl_hours),
        ip_hash=hash_ip(client_ip(request)), started_at=now,
    )
    db.add(s)
    await db.commit()
    await audit("session.start", request, user_id=user.id, patient_id=patient.id,
                resource_type="session", resource_id=s.id, detail={"purpose": body.purpose})
    return SessionStartOut(session=SessionOut.model_validate(s), ws_ticket=create_ws_ticket(user.id, s.id))


@router.get("/sessions/{session_id}", response_model=SessionOut)
async def get_session(session_id: uuid.UUID, user: CurrentUser, db: DB):
    return await _session_for(db, user, session_id, allow_owner=True)


@router.post("/sessions/{session_id}/ticket", response_model=TicketOut)
async def reissue_ticket(session_id: uuid.UUID, user: CurrentUser, db: DB):
    """Fresh short-lived WS ticket for reconnects (network blips, instance restarts)."""
    s = await _session_for(db, user, session_id)
    if not s.consent_valid():
        raise HTTPException(status.HTTP_403_FORBIDDEN, "consent expired or revoked")
    p = await db.get(Patient, s.patient_id)
    if p is None or await role_for(db, user.id, p) not in ("owner", "editor"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "access to patient revoked")
    return TicketOut(ws_ticket=create_ws_ticket(user.id, s.id), ws_path="/ws/ingest")


@router.post("/patients/{patient_id}/watch-ticket", response_model=TicketOut)
async def watch_ticket(patient_id: uuid.UUID, user: CurrentUser, db: DB):
    """Ticket for /ws/watch: live alert stream for a patient from any device/instance."""
    p, _ = await patient_access(db, user, patient_id)
    return TicketOut(ws_ticket=create_ws_ticket(user.id, p.id, purpose="watch"), ws_path="/ws/watch")


@router.post("/sessions/{session_id}/end", response_model=SessionOut)
async def end_session(session_id: uuid.UUID, request: Request, user: CurrentUser, db: DB):
    s = await _session_for(db, user, session_id, allow_owner=True)
    if s.status == "active":
        s.status, s.ended_at = "ended", utcnow()
        await db.commit()
        await audit("session.end", request, user_id=user.id, patient_id=s.patient_id,
                    resource_type="session", resource_id=s.id)
    return s


@router.post("/sessions/{session_id}/revoke", response_model=SessionOut)
async def revoke_consent(session_id: uuid.UUID, request: Request, user: CurrentUser, db: DB):
    """Withdraw consent: stream is refused immediately (checked on every batch flush)."""
    s = await _session_for(db, user, session_id, allow_owner=True)
    now = utcnow()
    s.status, s.consent_revoked_at = "revoked", now
    s.ended_at = s.ended_at or now
    await db.commit()
    await audit("session.consent_revoke", request, user_id=user.id, patient_id=s.patient_id,
                resource_type="session", resource_id=s.id)
    return s


@router.post("/alerts/{alert_id}/ack", response_model=AlertOut)
async def acknowledge_alert(alert_id: uuid.UUID, request: Request, user: CurrentUser, db: DB):
    a = await db.get(Alert, alert_id)
    if a is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "alert not found")
    try:
        await patient_access(db, user, a.patient_id, "editor")
    except HTTPException as e:
        if e.status_code == 404:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "alert not found") from None
        raise
    if a.acknowledged_at is None:
        a.acknowledged_at, a.acknowledged_by = utcnow(), user.id
        await db.commit()
        await audit("alert.ack", request, user_id=user.id, patient_id=a.patient_id,
                    resource_type="alert", resource_id=a.id)
    return a
