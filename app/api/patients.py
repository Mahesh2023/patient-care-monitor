"""Patients (pseudonymous), their alert history, metrics and GDPR export."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, UTC
from typing import Optional

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import select

from ..deps import DB, CurrentUser, owned_patient, rate_limit
from ..models import Alert, MonitoringSession, Patient, SessionMetric
from ..schemas import AlertOut, MetricOut, PatientExport, PatientIn, PatientOut, SessionOut

router = APIRouter(prefix="/api/patients", tags=["patients"],
                   dependencies=[Depends(rate_limit("api", "api_rate_per_minute"))])


@router.get("", response_model=list[PatientOut])
async def list_patients(user: CurrentUser, db: DB,
                        limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0)):
    q = (select(Patient).where(Patient.owner_id == user.id)
         .order_by(Patient.created_at.desc()).limit(limit).offset(offset))
    return (await db.execute(q)).scalars().all()


@router.post("", response_model=PatientOut, status_code=201)
async def create_patient(body: PatientIn, user: CurrentUser, db: DB):
    p = Patient(owner_id=user.id, display_name=body.display_name.strip(), notes=body.notes)
    db.add(p)
    await db.commit()
    return p


@router.get("/{patient_id}", response_model=PatientOut)
async def get_patient(patient_id: uuid.UUID, user: CurrentUser, db: DB):
    return await owned_patient(db, user, patient_id)


@router.put("/{patient_id}", response_model=PatientOut)
async def update_patient(patient_id: uuid.UUID, body: PatientIn, user: CurrentUser, db: DB):
    p = await owned_patient(db, user, patient_id)
    p.display_name, p.notes = body.display_name.strip(), body.notes
    await db.commit()
    return p


@router.delete("/{patient_id}", status_code=204)
async def delete_patient(patient_id: uuid.UUID, user: CurrentUser, db: DB) -> Response:
    """GDPR erasure: cascades to sessions, alerts and metrics."""
    await db.delete(await owned_patient(db, user, patient_id))
    await db.commit()
    return Response(status_code=204)


@router.get("/{patient_id}/alerts", response_model=list[AlertOut])
async def patient_alerts(patient_id: uuid.UUID, user: CurrentUser, db: DB,
                         unacknowledged: bool = False,
                         before: Optional[datetime] = None,
                         limit: int = Query(50, ge=1, le=200)):
    await owned_patient(db, user, patient_id)
    q = select(Alert).where(Alert.patient_id == patient_id)
    if unacknowledged:
        q = q.where(Alert.acknowledged_at.is_(None))
    if before:
        q = q.where(Alert.created_at < before)  # keyset pagination
    return (await db.execute(q.order_by(Alert.created_at.desc()).limit(limit))).scalars().all()


@router.get("/{patient_id}/metrics", response_model=list[MetricOut])
async def patient_metrics(patient_id: uuid.UUID, user: CurrentUser, db: DB,
                          hours: int = Query(24, ge=1, le=24 * 30)):
    await owned_patient(db, user, patient_id)
    since = datetime.now(UTC) - timedelta(hours=hours)
    q = (select(SessionMetric)
         .where(SessionMetric.patient_id == patient_id, SessionMetric.bucket_start >= since)
         .order_by(SessionMetric.bucket_start).limit(5000))
    return (await db.execute(q)).scalars().all()


@router.get("/{patient_id}/sessions", response_model=list[SessionOut])
async def patient_sessions(patient_id: uuid.UUID, user: CurrentUser, db: DB,
                           limit: int = Query(20, ge=1, le=100)):
    await owned_patient(db, user, patient_id)
    q = (select(MonitoringSession).where(MonitoringSession.patient_id == patient_id)
         .order_by(MonitoringSession.started_at.desc()).limit(limit))
    return (await db.execute(q)).scalars().all()


@router.get("/{patient_id}/export", response_model=PatientExport)
async def export_patient(patient_id: uuid.UUID, user: CurrentUser, db: DB):
    """GDPR Art. 15/20 data portability (numeric data only — no media exists)."""
    p = await owned_patient(db, user, patient_id)
    sessions = (await db.execute(select(MonitoringSession).where(MonitoringSession.patient_id == p.id)
                                 .order_by(MonitoringSession.started_at))).scalars().all()
    alerts = (await db.execute(select(Alert).where(Alert.patient_id == p.id)
                               .order_by(Alert.created_at))).scalars().all()
    metrics = (await db.execute(select(SessionMetric).where(SessionMetric.patient_id == p.id)
                                .order_by(SessionMetric.bucket_start))).scalars().all()
    return PatientExport(
        patient=PatientOut.model_validate(p),
        sessions=[SessionOut.model_validate(s) for s in sessions],
        alerts=[AlertOut.model_validate(a) for a in alerts],
        metrics=[MetricOut.model_validate(m) for m in metrics],
        policy="Raw video/audio never leaves the caregiver's browser. Only per-minute "
               "numeric aggregates and alert records are stored.",
    )
