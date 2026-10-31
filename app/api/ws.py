"""WebSocket endpoints.

/ws/ingest?ticket=…  browser -> numeric feature batches -> analysis results
/ws/watch?ticket=…   live alert stream for a patient (fan-out via KV pub/sub,
                     so a caregiver on any device/instance sees alerts raised
                     by a stream on any other instance)

Scaling properties of /ws/ingest:
  * no DB connection held for the socket lifetime — short transactions only,
    flushed every FLUSH_INTERVAL_S (alerts, per-minute rollups, sample count);
  * consent revocation is re-checked on every flush (<= FLUSH_INTERVAL_S lag);
  * per-connection token bucket + max message size + schema validation;
  * per-user concurrent stream cap enforced through the shared KV;
  * all pipeline state is bounded; on reconnect (any instance) it rebuilds
    within a few seconds — no sticky sessions required.
"""
from __future__ import annotations

import asyncio
import contextlib
import time
import uuid
from datetime import datetime, UTC
from typing import Any, Optional

import orjson
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import update

from src.care_monitor.config import settings
from src.care_monitor.inference.llm_reasoner import get_reasoner
from src.care_monitor.logging_utils import get_logger
from src.care_monitor.pipeline import ProtocolError, SessionPipeline, handshake

from ..core import metrics as m
from ..core.audit import audit
from ..core.db import SessionLocal
from ..core.kv import kv
from ..core.security import TokenError, decode_token
from ..deps import role_for
from ..models import Alert, MonitoringSession, Patient, SessionMetric

router = APIRouter()
log = get_logger(__name__)
FLUSH_INTERVAL_S = 5.0
STREAM_COUNTER_TTL_S = 6 * 3600


def alert_channel(patient_id: uuid.UUID | str) -> str:
    return f"alerts:{patient_id}"


class _TokenBucket:
    def __init__(self, rate: float, burst: float) -> None:
        self.rate, self.burst, self.tokens, self.t = rate, burst, burst, time.monotonic()

    def take(self) -> bool:
        now = time.monotonic()
        self.tokens = min(self.burst, self.tokens + (now - self.t) * self.rate)
        self.t = now
        if self.tokens >= 1.0:
            self.tokens -= 1.0
            return True
        return False


async def _close(ws: WebSocket, code: int, reason: str) -> None:
    with contextlib.suppress(Exception):
        await ws.send_text(orjson.dumps({"type": "error", "code": reason}).decode())
        await ws.close(code=code, reason=reason)


def _ticket(ws: WebSocket, purpose: str) -> Optional[dict[str, Any]]:
    try:
        claims = decode_token(ws.query_params.get("ticket", ""), "ws")
        if claims.get("pur") != purpose:
            return None
        claims["_uid"], claims["_sid"] = uuid.UUID(claims["sub"]), uuid.UUID(claims["sid"])
        return claims
    except (TokenError, KeyError, ValueError):
        return None


class _Ingest:
    def __init__(self, ws: WebSocket, session: MonitoringSession, patient: Patient) -> None:
        self.ws = ws
        self.sid = session.id
        self.uid = session.user_id
        self.patient_id = session.patient_id
        self.pipeline = SessionPipeline(str(session.id), baseline=patient.au_baseline,
                                        alert_config=patient.alert_settings)
        self.applied_settings = patient.alert_settings
        self.send_lock = asyncio.Lock()
        self.pending_alerts: list[Alert] = []
        self.pending_rollups: list[dict[str, Any]] = []
        self.flushed_samples = 0
        self.last_flush = time.monotonic()
        self.llm_task: Optional[asyncio.Task] = None
        self.reasoner = get_reasoner()

    async def send(self, obj: dict[str, Any]) -> None:
        async with self.send_lock:
            await self.ws.send_text(orjson.dumps(obj).decode())

    async def handle_batch(self, msg: dict[str, Any]) -> None:
        t0 = time.perf_counter()
        result = self.pipeline.process_batch(msg)
        m.WS_BATCH_LATENCY.observe(time.perf_counter() - t0)
        m.WS_BATCHES.inc()
        m.WS_SAMPLES.inc(result.samples)

        now = datetime.now(UTC)
        for a in result.alerts:
            row = Alert(id=uuid.uuid4(), session_id=self.sid, patient_id=self.patient_id,
                        key=a["key"], level=a["level"], reason=a["reason"][:300],
                        evidence={k: float(v) for k, v in a["evidence"].items()}, created_at=now)
            a["id"] = str(row.id)
            self.pending_alerts.append(row)
            m.ALERTS.labels(a["level"], a["key"]).inc()
            await kv.publish(alert_channel(self.patient_id), orjson.dumps({
                "type": "alert", "id": str(row.id), "session_id": str(self.sid),
                "patient_id": str(self.patient_id), "key": row.key, "level": row.level,
                "reason": row.reason, "created_at": now.isoformat(), "escalated": False,
            }).decode())
        rollup = self.pipeline.pop_rollup()
        if rollup:
            self.pending_rollups.append(rollup)

        await self.send({"type": "result", "data": result.to_dict()})

        if (self.reasoner.available() and (self.llm_task is None or self.llm_task.done())
                and self.pipeline.llm_due()):
            self.llm_task = asyncio.create_task(self._summarise(dict(self.pipeline.last_snapshot)))

    async def _summarise(self, snapshot: dict[str, Any]) -> None:
        text = await self.reasoner.reason(snapshot)
        m.LLM_CALLS.labels("ok" if text else "skipped").inc()
        if text:
            with contextlib.suppress(Exception):
                await self.send({"type": "summary", "text": text, "ts": time.time()})

    async def flush(self, final: bool = False) -> bool:
        """Persist buffered data and re-validate the stream.

        Returns False if consent was revoked/expired or the caregiver lost
        editor access to the patient. Also persists a freshly computed
        neutral-face baseline and hot-reloads changed alert settings.
        """
        self.last_flush = time.monotonic()
        if final:
            r = self.pipeline.pop_rollup(force=True)
            if r:
                self.pending_rollups.append(r)
        alerts, self.pending_alerts = self.pending_alerts, []
        rollups, self.pending_rollups = self.pending_rollups, []
        delta = self.pipeline.sample_count - self.flushed_samples
        new_baseline = self.pipeline.take_new_baseline()
        try:
            async with SessionLocal() as db:
                s = await db.get(MonitoringSession, self.sid)
                p = await db.get(Patient, self.patient_id)
                if s is None or p is None:
                    return False
                db.add_all(alerts)
                db.add_all(SessionMetric(
                    session_id=self.sid, patient_id=self.patient_id,
                    bucket_start=datetime.fromtimestamp(r.pop("bucket_start"), UTC), **r,
                ) for r in rollups)
                if delta:
                    await db.execute(update(MonitoringSession).where(MonitoringSession.id == self.sid)
                                     .values(sample_count=MonitoringSession.sample_count + delta))
                if new_baseline is not None:
                    p.au_baseline, p.baseline_updated_at = new_baseline, datetime.now(UTC)
                role = await role_for(db, self.uid, p)
                await db.commit()
                self.flushed_samples += delta
                if p.alert_settings != self.applied_settings:
                    self.pipeline.apply_alert_config(p.alert_settings)
                    self.applied_settings = p.alert_settings
                return s.consent_valid() and role in ("owner", "editor")
        except Exception as e:
            log.error("flush failed for session %s: %s", self.sid, e)
            # Re-queue (bounded) so a transient DB blip does not lose alerts.
            self.pending_alerts = (alerts + self.pending_alerts)[-200:]
            self.pending_rollups = (rollups + self.pending_rollups)[-60:]
            if new_baseline is not None:
                self.pipeline.baseline.fresh = True
            return True


@router.websocket("/ws/ingest")
async def ws_ingest(ws: WebSocket) -> None:
    await ws.accept()
    claims = _ticket(ws, "ingest")
    if claims is None:
        return await _close(ws, 4401, "invalid_ticket")
    uid, sid = claims["_uid"], claims["_sid"]
    async with SessionLocal() as db:
        session = await db.get(MonitoringSession, sid)
        patient = await db.get(Patient, session.patient_id) if session else None
        role = await role_for(db, uid, patient) if patient else None
    if session is None or patient is None or session.user_id != uid:
        return await _close(ws, 4404, "session_not_found")
    if role not in ("owner", "editor"):
        return await _close(ws, 4403, "forbidden")
    if not session.consent_valid():
        return await _close(ws, 4403, "consent_required")

    counter = f"streams:{uid}"
    if await kv.incr(counter, 1, STREAM_COUNTER_TTL_S) > settings.max_active_streams_per_user:
        await kv.incr(counter, -1, STREAM_COUNTER_TTL_S)
        return await _close(ws, 4429, "too_many_streams")

    m.WS_STREAMS.labels("ingest").inc()
    ing = _Ingest(ws, session, patient)
    bucket = _TokenBucket(settings.max_batches_per_second, settings.max_batches_per_second * 2)
    log.info("ingest stream opened session=%s", sid)
    ip = ws.client.host if ws.client else None
    await audit("session.stream_open", user_id=uid, patient_id=patient.id, resource_type="session",
                resource_id=sid, ip=ip)
    close_code, close_reason = 1000, "bye"
    try:
        await ing.send({"type": "hello", "session_id": str(sid), **handshake()})
        while True:
            try:
                raw = await asyncio.wait_for(ws.receive_text(), timeout=settings.websocket_receive_timeout)
            except TimeoutError:
                close_code, close_reason = 4408, "idle_timeout"
                break
            if len(raw) > settings.max_ws_message_bytes:
                m.WS_REJECTS.labels("too_large").inc()
                close_code, close_reason = 1009, "message_too_large"
                break
            if not bucket.take():
                m.WS_REJECTS.labels("rate").inc()
                await ing.send({"type": "throttled"})
                continue
            try:
                msg = orjson.loads(raw)
                if not isinstance(msg, dict):
                    raise ProtocolError("message must be an object")
                kind = msg.get("type")
                if kind == "ping":
                    await ing.send({"type": "pong", "ts": time.time()})
                elif kind == "batch":
                    await ing.handle_batch(msg)
                elif kind == "recalibrate":
                    ing.pipeline.recalibrate()
                    await ing.send({"type": "recalibrating"})
                else:
                    raise ProtocolError("unknown message type")
            except (ProtocolError, orjson.JSONDecodeError) as e:
                m.WS_REJECTS.labels("protocol").inc()
                await ing.send({"type": "error", "code": "protocol", "message": str(e)[:200]})
                continue
            if (time.monotonic() - ing.last_flush >= FLUSH_INTERVAL_S or ing.pending_alerts
                    or ing.pipeline.baseline.fresh):
                if not await ing.flush():
                    close_code, close_reason = 4403, "consent_revoked"
                    break
    except WebSocketDisconnect:
        close_code = 0
    except Exception as e:
        log.exception("ingest stream error session=%s: %s", sid, e)
        close_code, close_reason = 1011, "internal_error"
    finally:
        if ing.llm_task and not ing.llm_task.done():
            ing.llm_task.cancel()
        m.WS_STREAMS.labels("ingest").dec()
        log.info("ingest stream closed session=%s samples=%d", sid, ing.pipeline.sample_count)
        # Shielded: a cancelled handler must not abort the final write mid-transaction.
        final = asyncio.ensure_future(ing.flush(final=True))
        try:
            await asyncio.shield(final)
            if close_code:
                await _close(ws, close_code, close_reason)
        finally:
            await asyncio.shield(kv.incr(counter, -1, STREAM_COUNTER_TTL_S))
            await asyncio.shield(audit("session.stream_close", user_id=uid, patient_id=patient.id,
                                       resource_type="session", resource_id=sid, ip=ip,
                                       detail={"samples": ing.pipeline.sample_count}))


@router.websocket("/ws/watch")
async def ws_watch(ws: WebSocket) -> None:
    await ws.accept()
    claims = _ticket(ws, "watch")
    if claims is None:
        return await _close(ws, 4401, "invalid_ticket")
    uid, patient_id = claims["_uid"], claims["_sid"]
    async with SessionLocal() as db:
        p = await db.get(Patient, patient_id)
        role = await role_for(db, uid, p) if p else None
    if role is None:
        return await _close(ws, 4404, "patient_not_found")

    m.WS_STREAMS.labels("watch").inc()
    try:
        async with kv.subscribe(alert_channel(patient_id)) as q:
            await ws.send_text(orjson.dumps({"type": "hello", "patient_id": str(patient_id)}).decode())

            async def pump() -> None:
                while True:
                    await ws.send_text(await q.get())

            async def drain() -> None:  # detect client disconnect / ignore input
                while True:
                    await ws.receive_text()

            tasks = [asyncio.create_task(pump()), asyncio.create_task(drain())]
            _, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for t in pending:
                t.cancel()
    except WebSocketDisconnect:
        pass
    finally:
        m.WS_STREAMS.labels("watch").dec()
