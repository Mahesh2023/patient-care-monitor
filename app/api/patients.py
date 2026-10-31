"""Patients (pseudonymous): CRUD, history, alert settings, calibration, export, access log.

Access is role-based (owner / editor / viewer, see app.deps) and every read
or write of patient data is recorded in the audit trail.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy import select

from src.care_monitor.inference.alerts import AlertSettings

from ..core.audit import audit
from ..deps import DB, CurrentUser, patient_access, rate_limit
from ..models import Alert, AuditEvent, MonitoringSession, Patient, PatientMember, SessionMetric
from ..schemas import (
    AlertOut, AlertSettingsIn, AuditOut, MetricOut, PatientExport, PatientIn, PatientOut, SessionOut,
)

router = APIRouter(prefix="/api/patients", tags=["patients"],
                   dependencies=[Depends(rate_limit("api", "api_rate_per_minute"))])


def _out(p: Patient, role: str) -> PatientOut:
    o = PatientOut.model_validate(p)
    o.role = role
    return o


@router.get("", response_model=list[PatientOut])
async def list_patients(request: Request, user: CurrentUser, db: DB,
                        limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0)):
    owned = (await db.execute(select(Patient).where(Patient.owner_id == user.id))).scalars().all()
    shared = (await db.execute(
        select(Patient, PatientMember.role).join(PatientMember, PatientMember.patient_id == Patient.id)
        .where(PatientMember.user_id == user.id))).all()
    rows = [_out(p, "owner") for p in owned] + [_out(p, role) for p, role in shared]
    rows.sort(key=lambda o: o.created_at, reverse=True)
    await audit("patient.list", request, user_id=user.id)
    return rows[offset:offset + limit]


@router.post("", response_model=PatientOut, status_code=201)
async def create_patient(body: PatientIn, request: Request, user: CurrentUser, db: DB):
    p = Patient(owner_id=user.id, display_name=body.display_name.strip(), notes=body.notes)
    db.add(p)
    await db.commit()
    await audit("patient.create", request, user_id=user.id, patient_id=p.id)
    return _out(p, "owner")


@router.get("/{patient_id}", response_model=PatientOut)
async def get_patient(patient_id: uuid.UUID, request: Request, user: CurrentUser, db: DB):
    p, role = await patient_access(db, user, patient_id)
    await audit("patient.read", request, user_id=user.id, patient_id=p.id)
    return _out(p, role)


@router.put("/{patient_id}", response_model=PatientOut)
async def update_patient(patient_id: uuid.UUID, body: PatientIn, request: Request, user: CurrentUser, db: DB):
    p, role = await patient_access(db, user, patient_id, "owner")
    p.display_name, p.notes = body.display_name.strip(), body.notes
    await db.commit()
    await audit("patient.update", request, user_id=user.id, patient_id=p.id)
    return _out(p, role)


@router.delete("/{patient_id}", status_code=204)
async def delete_patient(patient_id: uuid.UUID, request: Request, user: CurrentUser, db: DB) -> Response:
    """GDPR erasure: cascades to sessions, alerts, metrics, events, assessments, team."""
    p, _ = await patient_access(db, user, patient_id, "owner")
    await db.delete(p)
    await db.commit()
    await audit("patient.delete", request, user_id=user.id, patient_id=patient_id)
    return Response(status_code=204)


@router.get("/{patient_id}/alerts", response_model=list[AlertOut])
async def patient_alerts(patient_id: uuid.UUID, request: Request, user: CurrentUser, db: DB,
                         unacknowledged: bool = False,
                         before: Optional[datetime] = None,
                         limit: int = Query(50, ge=1, le=200)):
    await patient_access(db, user, patient_id)
    q = select(Alert).where(Alert.patient_id == patient_id)
    if unacknowledged:
        q = q.where(Alert.acknowledged_at.is_(None))
    if before:
        q = q.where(Alert.created_at < before)  # keyset pagination
    rows = (await db.execute(q.order_by(Alert.created_at.desc()).limit(limit))).scalars().all()
    await audit("alerts.read", request, user_id=user.id, patient_id=patient_id)
    return rows


@router.get("/{patient_id}/metrics", response_model=list[MetricOut])
async def patient_metrics(patient_id: uuid.UUID, request: Request, user: CurrentUser, db: DB,
                          hours: int = Query(24, ge=1, le=24 * 30)):
    await patient_access(db, user, patient_id)
    since = datetime.now(UTC) - timedelta(hours=hours)
    q = (select(SessionMetric)
         .where(SessionMetric.patient_id == patient_id, SessionMetric.bucket_start >= since)
         .order_by(SessionMetric.bucket_start).limit(5000))
    rows = (await db.execute(q)).scalars().all()
    await audit("metrics.read", request, user_id=user.id, patient_id=patient_id)
    return rows


@router.get("/{patient_id}/sessions", response_model=list[SessionOut])
async def patient_sessions(patient_id: uuid.UUID, request: Request, user: CurrentUser, db: DB,
                           limit: int = Query(20, ge=1, le=100)):
    await patient_access(db, user, patient_id)
    q = (select(MonitoringSession).where(MonitoringSession.patient_id == patient_id)
         .order_by(MonitoringSession.started_at.desc()).limit(limit))
    rows = (await db.execute(q)).scalars().all()
    await audit("sessions.read", request, user_id=user.id, patient_id=patient_id)
    return rows


# ---- per-patient alarm configuration ---------------------------------
@router.get("/{patient_id}/alert-settings", response_model=AlertSettingsIn)
async def get_alert_settings(patient_id: uuid.UUID, user: CurrentUser, db: DB):
    p, _ = await patient_access(db, user, patient_id)
    return AlertSettingsIn(**AlertSettings.from_dict(p.alert_settings).to_dict())


@router.put("/{patient_id}/alert-settings", response_model=AlertSettingsIn)
async def put_alert_settings(patient_id: uuid.UUID, body: AlertSettingsIn, request: Request,
                             user: CurrentUser, db: DB):
    p, _ = await patient_access(db, user, patient_id, "owner")
    p.alert_settings = body.model_dump()
    await db.commit()  # live streams hot-reload on their next flush (<= 5 s)
    await audit("patient.alert_settings_update", request, user_id=user.id, patient_id=p.id,
                detail=p.alert_settings)
    return body


@router.delete("/{patient_id}/baseline", status_code=204)
async def reset_baseline(patient_id: uuid.UUID, request: Request, user: CurrentUser, db: DB) -> Response:
    """Discard the stored neutral-face baseline; the next session recalibrates."""
    p, _ = await patient_access(db, user, patient_id, "editor")
    p.au_baseline, p.baseline_updated_at = None, None
    await db.commit()
    await audit("patient.baseline_reset", request, user_id=user.id, patient_id=p.id)
    return Response(status_code=204)


# ---- data rights / accountability -------------------------------------
@router.get("/{patient_id}/export", response_model=PatientExport)
async def export_patient(patient_id: uuid.UUID, request: Request, user: CurrentUser, db: DB):
    """GDPR Art. 15/20 data portability (numeric data only — no media exists)."""
    p, role = await patient_access(db, user, patient_id, "owner")
    sessions = (await db.execute(select(MonitoringSession).where(MonitoringSession.patient_id == p.id)
                                 .order_by(MonitoringSession.started_at))).scalars().all()
    alerts = (await db.execute(select(Alert).where(Alert.patient_id == p.id)
                               .order_by(Alert.created_at))).scalars().all()
    metrics = (await db.execute(select(SessionMetric).where(SessionMetric.patient_id == p.id)
                                .order_by(SessionMetric.bucket_start))).scalars().all()
    await audit("patient.export", request, user_id=user.id, patient_id=p.id)
    return PatientExport(
        patient=_out(p, role),
        sessions=[SessionOut.model_validate(s) for s in sessions],
        alerts=[AlertOut.model_validate(a) for a in alerts],
        metrics=[MetricOut.model_validate(m) for m in metrics],
        policy="Raw video/audio never leaves the caregiver's browser. Only per-minute "
               "numeric aggregates, alerts, care events and assessments are stored.",
    )


@router.get("/{patient_id}/audit", response_model=list[AuditOut])
async def patient_audit(patient_id: uuid.UUID, user: CurrentUser, db: DB,
                        before: Optional[datetime] = None, limit: int = Query(100, ge=1, le=500)):
    """Who accessed this patient's data, when (owner only)."""
    await patient_access(db, user, patient_id, "owner")
    q = select(AuditEvent).where(AuditEvent.patient_id == patient_id)
    if before:
        q = q.where(AuditEvent.ts < before)
    return (await db.execute(q.order_by(AuditEvent.ts.desc()).limit(limit))).scalars().all()
