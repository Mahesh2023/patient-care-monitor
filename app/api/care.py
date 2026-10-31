"""Care team sharing, care events (+ before/after impact) and PAINAD assessments."""
from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy import select

from src.care_monitor.inference.painad import interpret

from ..core.audit import audit
from ..deps import DB, CurrentUser, patient_access, rate_limit
from ..models import CareEvent, MonitoringSession, PainadAssessment, PatientMember, SessionMetric, User, utcnow
from ..schemas import (
    CareEventIn, CareEventOut, ImpactOut, MemberIn, MemberOut, PainadIn, PainadOut, WindowStats,
)

router = APIRouter(prefix="/api/patients", tags=["care"],
                   dependencies=[Depends(rate_limit("api", "api_rate_per_minute"))])


# ---- care team ----------------------------------------------------------
@router.get("/{patient_id}/members", response_model=list[MemberOut])
async def list_members(patient_id: uuid.UUID, user: CurrentUser, db: DB):
    p, _ = await patient_access(db, user, patient_id)
    owner = await db.get(User, p.owner_id)
    rows = (await db.execute(select(PatientMember, User).join(User, User.id == PatientMember.user_id)
                             .where(PatientMember.patient_id == p.id)
                             .order_by(PatientMember.created_at))).all()
    out = [MemberOut(user_id=owner.id, email=owner.email, full_name=owner.full_name, role="owner",
                     created_at=p.created_at)]
    out += [MemberOut(user_id=u.id, email=u.email, full_name=u.full_name, role=m.role, created_at=m.created_at)
            for m, u in rows]
    return out


@router.post("/{patient_id}/members", response_model=MemberOut, status_code=201)
async def add_member(patient_id: uuid.UUID, body: MemberIn, request: Request, user: CurrentUser, db: DB):
    """Share a patient with another registered caregiver (owner only)."""
    p, _ = await patient_access(db, user, patient_id, "owner")
    target = (await db.execute(select(User).where(User.email == body.email.lower()))).scalar_one_or_none()
    if target is None or not target.is_active:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no active account with that email")
    if target.id == p.owner_id:
        raise HTTPException(status.HTTP_409_CONFLICT, "user is the owner")
    m = await db.get(PatientMember, (p.id, target.id))
    if m:
        m.role = body.role
    else:
        m = PatientMember(patient_id=p.id, user_id=target.id, role=body.role, invited_by=user.id)
        db.add(m)
    await db.commit()
    await audit("team.member_upsert", request, user_id=user.id, patient_id=p.id,
                resource_type="user", resource_id=target.id, detail={"role": body.role})
    return MemberOut(user_id=target.id, email=target.email, full_name=target.full_name, role=m.role,
                     created_at=m.created_at)


@router.delete("/{patient_id}/members/{member_id}", status_code=204)
async def remove_member(patient_id: uuid.UUID, member_id: uuid.UUID, request: Request,
                        user: CurrentUser, db: DB) -> Response:
    """Owner removes anyone; a member may remove themself (leave)."""
    p, role = await patient_access(db, user, patient_id)
    if role != "owner" and member_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "requires owner role")
    m = await db.get(PatientMember, (p.id, member_id))
    if m is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "member not found")
    await db.delete(m)
    await db.commit()
    await audit("team.member_remove", request, user_id=user.id, patient_id=p.id,
                resource_type="user", resource_id=member_id)
    return Response(status_code=204)


# ---- care events --------------------------------------------------------
@router.post("/{patient_id}/events", response_model=CareEventOut, status_code=201)
async def create_event(patient_id: uuid.UUID, body: CareEventIn, request: Request, user: CurrentUser, db: DB):
    p, _ = await patient_access(db, user, patient_id, "editor")
    now = utcnow()
    occurred = body.occurred_at or now
    if occurred.tzinfo is None:
        raise HTTPException(422, "occurred_at must include a timezone")
    if occurred > now + timedelta(minutes=5) or occurred < now - timedelta(days=7):
        raise HTTPException(422, "occurred_at must be within the last 7 days")
    ev = CareEvent(patient_id=p.id, user_id=user.id, kind=body.kind, note=body.note, occurred_at=occurred)
    db.add(ev)
    await db.commit()
    await audit("care_event.create", request, user_id=user.id, patient_id=p.id,
                resource_type="care_event", resource_id=ev.id)
    return ev


@router.get("/{patient_id}/events", response_model=list[CareEventOut])
async def list_events(patient_id: uuid.UUID, request: Request, user: CurrentUser, db: DB,
                      hours: int = Query(24 * 7, ge=1, le=24 * 30)):
    await patient_access(db, user, patient_id)
    since = utcnow() - timedelta(hours=hours)
    q = (select(CareEvent).where(CareEvent.patient_id == patient_id, CareEvent.occurred_at >= since)
         .order_by(CareEvent.occurred_at.desc()).limit(500))
    rows = (await db.execute(q)).scalars().all()
    await audit("care_event.read", request, user_id=user.id, patient_id=patient_id)
    return rows


def _stats(rows: list[SessionMetric], minutes: int) -> WindowStats:
    face = sum(r.face_samples for r in rows)

    def wavg(attr: str, weight: str = "face_samples") -> Optional[float]:
        pairs = [(getattr(r, attr), getattr(r, weight)) for r in rows if getattr(r, attr) is not None]
        w = sum(x[1] for x in pairs)
        return round(sum(v * n for v, n in pairs) / w, 3) if w else None

    def mean(attr: str) -> Optional[float]:
        vals = [getattr(r, attr) for r in rows if getattr(r, attr) is not None]
        return round(sum(vals) / len(vals), 1) if vals else None

    return WindowStats(minutes=minutes, face_samples=face, avg_pspi=wavg("avg_pspi") if face else None,
                       max_pspi=max((r.max_pspi for r in rows), default=None) if face else None,
                       avg_comfort=wavg("avg_comfort"), avg_hr=mean("avg_hr"), avg_rr=mean("avg_rr"),
                       alerts=sum(r.alerts for r in rows))


@router.get("/{patient_id}/events/{event_id}/impact", response_model=ImpactOut)
async def event_impact(patient_id: uuid.UUID, event_id: uuid.UUID, request: Request, user: CurrentUser, db: DB,
                       before_min: int = Query(30, ge=5, le=240), after_min: int = Query(60, ge=5, le=480)):
    """Compare monitored signals before vs. after a care event (e.g. analgesia)."""
    await patient_access(db, user, patient_id)
    ev = await db.get(CareEvent, event_id)
    if ev is None or ev.patient_id != patient_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "event not found")
    t = ev.occurred_at

    async def window(a, b):
        q = select(SessionMetric).where(SessionMetric.patient_id == patient_id,
                                        SessionMetric.bucket_start >= a, SessionMetric.bucket_start < b)
        return list((await db.execute(q)).scalars().all())

    before = _stats(await window(t - timedelta(minutes=before_min), t), before_min)
    after = _stats(await window(t, t + timedelta(minutes=after_min)), after_min)
    await audit("care_event.impact_read", request, user_id=user.id, patient_id=patient_id,
                resource_type="care_event", resource_id=event_id)

    def delta(a, b):
        return round(b - a, 3) if a is not None and b is not None else None

    return ImpactOut(event=CareEventOut.model_validate(ev), before=before, after=after,
                     delta_avg_pspi=delta(before.avg_pspi, after.avg_pspi),
                     delta_avg_comfort=delta(before.avg_comfort, after.avg_comfort))


# ---- PAINAD assessments -------------------------------------------------
def _painad_out(a: PainadAssessment) -> PainadOut:
    o = PainadOut.model_validate(a)
    o.interpretation = interpret(a.total)
    return o


@router.post("/{patient_id}/assessments", response_model=PainadOut, status_code=201)
async def create_assessment(patient_id: uuid.UUID, body: PainadIn, request: Request, user: CurrentUser, db: DB):
    p, _ = await patient_access(db, user, patient_id, "editor")
    if body.session_id:
        s = await db.get(MonitoringSession, body.session_id)
        if s is None or s.patient_id != p.id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "session not found")
    total = (body.breathing + body.negative_vocalization + body.facial_expression
             + body.body_language + body.consolability)
    a = PainadAssessment(patient_id=p.id, session_id=body.session_id, user_id=user.id,
                         breathing=body.breathing, negative_vocalization=body.negative_vocalization,
                         facial_expression=body.facial_expression, body_language=body.body_language,
                         consolability=body.consolability, total=total,
                         auto_items=body.auto_items, note=body.note)
    db.add(a)
    await db.commit()
    await audit("painad.create", request, user_id=user.id, patient_id=p.id,
                resource_type="painad", resource_id=a.id, detail={"total": total})
    return _painad_out(a)


@router.get("/{patient_id}/assessments", response_model=list[PainadOut])
async def list_assessments(patient_id: uuid.UUID, request: Request, user: CurrentUser, db: DB,
                           limit: int = Query(50, ge=1, le=200)):
    await patient_access(db, user, patient_id)
    q = (select(PainadAssessment).where(PainadAssessment.patient_id == patient_id)
         .order_by(PainadAssessment.created_at.desc()).limit(limit))
    rows = (await db.execute(q)).scalars().all()
    await audit("painad.read", request, user_id=user.id, patient_id=patient_id)
    return [_painad_out(a) for a in rows]
