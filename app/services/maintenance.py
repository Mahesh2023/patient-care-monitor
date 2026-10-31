"""Periodic maintenance: retention enforcement + session hygiene.

Runs inside every web worker but is guarded by a distributed KV lock, so
exactly one process in the whole fleet executes each cycle (no separate
worker service needed on the free tier; can move to a Render Cron Job later).
"""
from __future__ import annotations

import asyncio
from datetime import timedelta

import orjson
from sqlalchemy import delete, select, update

from src.care_monitor.config import settings
from src.care_monitor.logging_utils import get_logger

from ..core.db import SessionLocal
from ..core.kv import kv
from ..models import Alert, AuditEvent, MonitoringSession, RefreshToken, SessionMetric, utcnow

log = get_logger(__name__)


async def run_once() -> dict:
    now = utcnow()
    async with SessionLocal() as db:
        r_metrics = await db.execute(delete(SessionMetric).where(
            SessionMetric.bucket_start < now - timedelta(days=settings.metrics_retention_days)))
        r_alerts = await db.execute(delete(Alert).where(
            Alert.created_at < now - timedelta(days=settings.alerts_retention_days)))
        r_tokens = await db.execute(delete(RefreshToken).where(RefreshToken.expires_at < now))
        r_audit = await db.execute(delete(AuditEvent).where(
            AuditEvent.ts < now - timedelta(days=settings.audit_retention_days)))
        r_sessions = await db.execute(
            update(MonitoringSession)
            .where(MonitoringSession.status == "active", MonitoringSession.consent_expires_at < now)
            .values(status="ended", ended_at=now))
        await db.commit()
    stats = {"metrics_deleted": r_metrics.rowcount, "alerts_deleted": r_alerts.rowcount,
             "tokens_deleted": r_tokens.rowcount, "audit_deleted": r_audit.rowcount,
             "sessions_expired": r_sessions.rowcount}
    log.info("maintenance: %s", stats)
    return stats


async def escalate_once() -> int:
    """Re-notify unacknowledged alerts (AAMI: alarm escalation for unanswered alarms).

    URGENT alerts unacknowledged after N minutes (and CONCERN after M) are
    re-published on the patient's live channel with `escalated: true`, so
    every care-team member watching on any device/instance is notified.
    Each alert escalates once (escalated_at).
    """
    from ..api.ws import alert_channel  # avoid import cycle at module load
    now = utcnow()
    rules = (("urgent", settings.alert_escalation_urgent_minutes),
             ("concern", settings.alert_escalation_concern_minutes))
    sent = 0
    async with SessionLocal() as db:
        for level, minutes in rules:
            q = (select(Alert).where(Alert.level == level, Alert.acknowledged_at.is_(None),
                                     Alert.escalated_at.is_(None),
                                     Alert.created_at < now - timedelta(minutes=minutes))
                 .order_by(Alert.created_at).limit(500))
            for a in (await db.execute(q)).scalars().all():
                a.escalated_at = now
                await kv.publish(alert_channel(a.patient_id), orjson.dumps({
                    "type": "alert", "id": str(a.id), "session_id": str(a.session_id),
                    "patient_id": str(a.patient_id), "key": a.key,
                    "level": "urgent", "original_level": a.level, "escalated": True,
                    "reason": f"UNACKNOWLEDGED for {minutes:.0f}+ min: {a.reason}"[:300],
                    "created_at": a.created_at.isoformat(),
                }).decode())
                sent += 1
        await db.commit()
    if sent:
        log.info("escalated %d unacknowledged alerts", sent)
    return sent


async def escalation_loop() -> None:
    interval = settings.escalation_interval_seconds
    while True:
        await asyncio.sleep(interval)
        try:
            if await kv.acquire_lock("lock:escalation", max(5, interval - 5)):
                await escalate_once()
        except asyncio.CancelledError:
            raise
        except Exception as e:
            log.error("escalation failed: %s", e)


async def maintenance_loop() -> None:
    interval = settings.maintenance_interval_seconds
    await asyncio.sleep(30)  # let the app finish booting
    while True:
        try:
            if await kv.acquire_lock("lock:maintenance", max(60, interval - 30)):
                await run_once()
        except asyncio.CancelledError:
            raise
        except Exception as e:
            log.error("maintenance failed: %s", e)
        await asyncio.sleep(interval)
