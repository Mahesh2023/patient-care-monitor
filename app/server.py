"""FastAPI + WebSocket server for CARE-MM.

Endpoints:
  GET  /                      -> HTML dashboard (single-page, embedded)
  GET  /health                -> liveness
  GET  /metrics               -> Prometheus metrics
  GET  /openapi.json, /docs
  POST /api/consent           -> grant consent, returns {session_id}
  POST /api/consent/revoke    -> revoke + delete session data
  POST /api/data/export       -> GDPR export (numeric only)
  POST /api/data/delete       -> GDPR delete
  WS   /ws?session_id=...     -> JPEG-frame -> analysis JSON
"""
from __future__ import annotations
import asyncio
import base64
import time
import uuid
from contextlib import asynccontextmanager
from typing import Dict, Optional

import cv2
import numpy as np
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, Response
from pydantic import BaseModel, Field

from src.care_monitor.agent import CareMonitorAgent
from src.care_monitor.config import settings
from src.care_monitor.logging_utils import get_logger
from src.care_monitor.perception.face_mesh import ensure_model
from src.care_monitor.privacy import CONSENT

from .dashboard_html import DASHBOARD_HTML

log = get_logger(__name__)


# ------------------ optional Prometheus (graceful if missing) -------
_PROM = None
if settings.enable_prometheus:
    try:
        from prometheus_client import Counter, Gauge, Histogram, generate_latest, CONTENT_TYPE_LATEST
        _PROM = {
            "frames": Counter("care_mm_frames_total", "Frames processed", ["session_id"]),
            "latency": Histogram("care_mm_frame_latency_seconds", "Per-frame analysis latency"),
            "sessions": Gauge("care_mm_active_sessions", "Active sessions"),
            "alerts": Counter("care_mm_alerts_total", "Alerts fired", ["level", "key"]),
            "generate_latest": generate_latest,
            "CONTENT_TYPE_LATEST": CONTENT_TYPE_LATEST,
        }
    except ImportError:
        log.warning("prometheus_client not installed — /metrics disabled.")


# ------------------ session registry --------------------------------
class SessionRegistry:
    def __init__(self) -> None:
        self._sessions: Dict[str, CareMonitorAgent] = {}
        self._last_activity: Dict[str, float] = {}
        self._start: Dict[str, float] = {}

    def get_or_create(self, sid: str) -> CareMonitorAgent:
        if sid not in self._sessions:
            self._sessions[sid] = CareMonitorAgent(session_id=sid)
            self._start[sid] = time.time()
            if _PROM:
                _PROM["sessions"].set(len(self._sessions))
            log.info(f"Session created: {sid}")
        self._last_activity[sid] = time.time()
        return self._sessions[sid]

    def remove(self, sid: str) -> None:
        a = self._sessions.pop(sid, None)
        self._last_activity.pop(sid, None)
        self._start.pop(sid, None)
        if a:
            try:
                a.close()
            except Exception:
                pass
        if _PROM:
            _PROM["sessions"].set(len(self._sessions))

    async def gc_loop(self) -> None:
        while True:
            await asyncio.sleep(60)
            now = time.time()
            expired = [sid for sid, t in self._last_activity.items()
                       if now - t > settings.session_timeout_seconds]
            for sid in expired:
                log.info(f"Session expired: {sid}")
                self.remove(sid)
            CONSENT.prune_expired()

    def __len__(self) -> int:
        return len(self._sessions)


SESSIONS = SessionRegistry()


# ------------------ lifecycle ---------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        ensure_model()
        log.info("MediaPipe FaceLandmarker model ready.")
    except Exception as e:
        log.warning(f"Model prefetch failed (will retry on first use): {e}")
    gc_task = asyncio.create_task(SESSIONS.gc_loop())
    try:
        yield
    finally:
        gc_task.cancel()
        for sid in list(SESSIONS._sessions.keys()):
            SESSIONS.remove(sid)


app = FastAPI(
    title="CARE-MM: Clinically-grounded Multimodal Patient Monitor",
    description=(
        "FACS-grounded, LLM-augmented, privacy-first multimodal distress "
        "monitoring for non-verbal clinical populations. "
        "Not FDA-approved; research / educational use only."
    ),
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ------------------ root / health / metrics -------------------------
@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def root() -> HTMLResponse:
    return HTMLResponse(content=DASHBOARD_HTML)


@app.get("/health", tags=["health"])
async def health() -> Dict:
    return {
        "status": "ok",
        "service": "care-mm",
        "version": "2.0.0",
        "active_sessions": len(SESSIONS),
        "llm_provider": settings.llm_provider,
        "llm_enabled": settings.enable_llm_reasoning,
    }


@app.get("/metrics", include_in_schema=False)
async def metrics():
    if not _PROM:
        return Response("# prometheus not installed\n", media_type="text/plain")
    return Response(_PROM["generate_latest"](), media_type=_PROM["CONTENT_TYPE_LATEST"])


# ------------------ consent + GDPR ---------------------------------
class ConsentGrant(BaseModel):
    purpose: str = Field(default="clinical_monitoring", max_length=128)
    session_id: Optional[str] = None


class SessionScoped(BaseModel):
    session_id: str


@app.post("/api/consent", tags=["consent"])
async def grant_consent(req: ConsentGrant, request: Request):
    ip_hash = str(hash(request.client.host if request.client else "unknown"))[:16]
    rec = CONSENT.grant(session_id=req.session_id, purpose=req.purpose, ip_hash=ip_hash)
    return {
        "session_id": rec.session_id,
        "granted_at": rec.granted_at,
        "expires_at": rec.granted_at + rec.ttl_seconds,
        "purpose": rec.purpose,
    }


@app.post("/api/consent/revoke", tags=["consent"])
async def revoke_consent(req: SessionScoped):
    revoked = CONSENT.revoke(req.session_id)
    SESSIONS.remove(req.session_id)
    return {"revoked": revoked, "session_id": req.session_id}


@app.post("/api/data/export", tags=["data"])
async def export_data(req: SessionScoped):
    if req.session_id not in SESSIONS._sessions:
        raise HTTPException(404, "session not found")
    a = SESSIONS._sessions[req.session_id]
    return {
        "session_id": req.session_id,
        "started_at": SESSIONS._start.get(req.session_id),
        "last_activity": SESSIONS._last_activity.get(req.session_id),
        "frame_count": a._frame_count,
        "consent_valid": CONSENT.is_valid(req.session_id),
        "policy": "Only numeric signals are ever persisted; raw frames are discarded after analysis.",
    }


@app.post("/api/data/delete", tags=["data"])
async def delete_data(req: SessionScoped):
    SESSIONS.remove(req.session_id)
    CONSENT.revoke(req.session_id)
    return {"deleted": True, "session_id": req.session_id}


# ------------------ WebSocket --------------------------------------
FRAME_INTERVAL = 1.0 / settings.max_fps_per_session


@app.websocket("/ws")
async def ws(websocket: WebSocket, session_id: Optional[str] = None):
    await websocket.accept()
    sid = session_id or str(uuid.uuid4())

    if not CONSENT.is_valid(sid):
        await websocket.send_json({
            "type": "error",
            "code": "consent_required",
            "message": "POST /api/consent before opening /ws.",
        })
        await websocket.close(code=4403)
        return

    agent = SESSIONS.get_or_create(sid)
    last_frame_t = 0.0
    start = time.time()
    await websocket.send_json({"type": "connected", "session_id": sid})

    try:
        while True:
            now = time.time()
            if now - last_frame_t < FRAME_INTERVAL:
                await asyncio.sleep(FRAME_INTERVAL - (now - last_frame_t))
            last_frame_t = now

            try:
                data = await asyncio.wait_for(
                    websocket.receive_json(),
                    timeout=settings.websocket_receive_timeout,
                )
            except asyncio.TimeoutError:
                log.info(f"WS idle timeout: {sid}")
                break

            if data.get("type") == "ping":
                await websocket.send_json({"type": "pong"})
                continue

            b64 = data.get("frame")
            if not b64:
                continue
            try:
                jpeg_bytes = base64.b64decode(b64)
                frame = cv2.imdecode(np.frombuffer(jpeg_bytes, np.uint8), cv2.IMREAD_COLOR)
                if frame is None:
                    continue
            except Exception as e:
                log.debug(f"decode error: {e}")
                continue

            t0 = time.time()
            result = agent.analyze(frame)
            dt = time.time() - t0
            if _PROM:
                _PROM["frames"].labels(session_id=sid).inc()
                _PROM["latency"].observe(dt)
                for a in result.alerts:
                    _PROM["alerts"].labels(level=a["level"], key=a["key"]).inc()

            SESSIONS._last_activity[sid] = time.time()
            try:
                await websocket.send_json({"type": "frame", "data": result.to_dict()})
            except Exception as e:
                log.info(f"send error ({sid}): {e}")
                break
    except WebSocketDisconnect:
        log.info(f"WS disconnected: {sid}")
    except Exception as e:
        log.error(f"WS error ({sid}): {e}")
    finally:
        # Don't auto-remove — the gc loop + explicit /revoke handle it.
        log.info(f"WS closed for session {sid} after {time.time() - start:.1f}s")


def run() -> None:
    import uvicorn
    uvicorn.run("app.server:app", host="0.0.0.0", port=8000, reload=False)


if __name__ == "__main__":
    run()
