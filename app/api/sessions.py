"""Monitoring sessions: consent-gated start, WS tickets, end, revoke; alert ack."""
from __future__ import annotations

import uuid
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, status

from src.care_monitor.config import settings
from src.care_monitor.privacy import hash_ip

from ..core.security import create_ws_ticket
from ..deps import DB, CurrentUser, client_ip, owned_patient, rate_limit
from ..models import Alert, MonitoringSession, Patient, User, utcnow
from ..schemas import AlertOut, SessionOut, SessionStartIn, SessionStartOut, TicketOut

router = APIRouter(prefix="/api", tags=["sessions"],
                   dependencies=[Depends(rate_limit("api", "api_rate_per_minute"))])


async def _owned_session(db: DB, user: User, session_id: uuid.UUID) -> MonitoringSession:
    s = await db.get(MonitoringSession, session_id)
    if s is None or s.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "session not found")
    return s


@router.post("/sessions", response_model=SessionStartOut, status_code=201)
async def start_session(body: SessionStartIn, request: Request, user: CurrentUser, db: DB):
    if not body.consent_confirmed:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "informed consent must be confirmed")
    patient = await owned_patient(db, user, body.patient_id)
    now = utcnow()
    s = MonitoringSession(
        patient_id=patient.id, user_id=user.id, consent_purpose=body.purpose,
        consent_granted_at=now, consent_expires_at=now + timedelta(hours=settings.consent_ttl_hours),
        ip_hash=hash_ip(client_ip(request)), started_at=now,
    )
    db.add(s)
    await db.commit()
    return SessionStartOut(session=SessionOut.model_validate(s),
                           ws_ticket=create_ws_ticket(user.id, s.id))


@router.get("/sessions/{session_id}", response_model=SessionOut)
async def get_session(session_id: uuid.UUID, user: CurrentUser, db: DB):
    return await _owned_session(db, user, session_id)


@router.post("/sessions/{session_id}/ticket", response_model=TicketOut)
async def reissue_ticket(session_id: uuid.UUID, user: CurrentUser, db: DB):
    """Fresh short-lived WS ticket for reconnects (network blips, instance restarts)."""
    s = await _owned_session(db, user, session_id)
    if not s.consent_valid():
        raise HTTPException(status.HTTP_403_FORBIDDEN, "consent expired or revoked")
    return TicketOut(ws_ticket=create_ws_ticket(user.id, s.id), ws_path="/ws/ingest")


@router.post("/patients/{patient_id}/watch-ticket", response_model=TicketOut)
async def watch_ticket(patient_id: uuid.UUID, user: CurrentUser, db: DB):
    """Ticket for /ws/watch: live alert stream for a patient from any device/instance."""
    p: Patient = await owned_patient(db, user, patient_id)
    return TicketOut(ws_ticket=create_ws_ticket(user.id, p.id, purpose="watch"), ws_path="/ws/watch")


@router.post("/sessions/{session_id}/end", response_model=SessionOut)
async def end_session(session_id: uuid.UUID, user: CurrentUser, db: DB):
    s = await _owned_session(db, user, session_id)
    if s.status == "active":
        s.status, s.ended_at = "ended", utcnow()
        await db.commit()
    return s


@router.post("/sessions/{session_id}/revoke", response_model=SessionOut)
async def revoke_consent(session_id: uuid.UUID, user: CurrentUser, db: DB):
    """Withdraw consent: stream is refused immediately (checked on every batch flush)."""
    s = await _owned_session(db, user, session_id)
    now = utcnow()
    s.status, s.consent_revoked_at = "revoked", now
    s.ended_at = s.ended_at or now
    await db.commit()
    return s


@router.post("/alerts/{alert_id}/ack", response_model=AlertOut)
async def acknowledge_alert(alert_id: uuid.UUID, user: CurrentUser, db: DB):
    a = await db.get(Alert, alert_id)
    p = await db.get(Patient, a.patient_id) if a else None
    if a is None or p is None or p.owner_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "alert not found")
    if a.acknowledged_at is None:
        a.acknowledged_at, a.acknowledged_by = utcnow(), user.id
        await db.commit()
    return a
