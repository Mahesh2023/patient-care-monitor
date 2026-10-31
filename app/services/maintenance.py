"""Periodic maintenance: retention enforcement + session hygiene.

Runs inside every web worker but is guarded by a distributed KV lock, so
exactly one process in the whole fleet executes each cycle (no separate
worker service needed on the free tier; can move to a Render Cron Job later).
"""
from __future__ import annotations

import asyncio
from datetime import timedelta

from sqlalchemy import delete, update

from src.care_monitor.config import settings
from src.care_monitor.logging_utils import get_logger

from ..core.db import SessionLocal
from ..core.kv import kv
from ..models import Alert, MonitoringSession, RefreshToken, SessionMetric, utcnow

log = get_logger(__name__)


async def run_once() -> dict:
    now = utcnow()
    async with SessionLocal() as db:
        r_metrics = await db.execute(delete(SessionMetric).where(
            SessionMetric.bucket_start < now - timedelta(days=settings.metrics_retention_days)))
        r_alerts = await db.execute(delete(Alert).where(
            Alert.created_at < now - timedelta(days=settings.alerts_retention_days)))
        r_tokens = await db.execute(delete(RefreshToken).where(RefreshToken.expires_at < now))
        r_sessions = await db.execute(
            update(MonitoringSession)
            .where(MonitoringSession.status == "active", MonitoringSession.consent_expires_at < now)
            .values(status="ended", ended_at=now))
        await db.commit()
    stats = {"metrics_deleted": r_metrics.rowcount, "alerts_deleted": r_alerts.rowcount,
             "tokens_deleted": r_tokens.rowcount, "sessions_expired": r_sessions.rowcount}
    log.info("maintenance: %s", stats)
    return stats


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
