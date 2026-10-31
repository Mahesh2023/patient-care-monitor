"""Liveness, readiness, metrics."""
from __future__ import annotations

import hmac

from fastapi import APIRouter, Header, HTTPException, Response
from fastapi.responses import JSONResponse
from sqlalchemy import text

from src.care_monitor.config import settings
from src.care_monitor.inference.llm_reasoner import get_reasoner
from src.care_monitor.logging_utils import get_logger

from ..core.db import engine
from ..core.kv import kv
from ..core.metrics import render_metrics

router = APIRouter(tags=["health"])
log = get_logger(__name__)


@router.get("/health")
async def health() -> dict:
    """Liveness: process is up (used by Render health checks; no dependencies)."""
    return {"status": "ok", "service": "care-mm", "version": settings.app_version}


@router.get("/ready")
async def ready() -> JSONResponse:
    """Readiness: dependencies reachable."""
    checks = {"database": False, "kv": False}
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        checks["database"] = True
    except Exception as e:
        log.warning("readiness: database unreachable: %s", type(e).__name__)
    checks["kv"] = await kv.ping()
    ok = all(checks.values())
    return JSONResponse(
        {"status": "ready" if ok else "degraded", "checks": checks, "kv_backend": kv.backend,
         "llm_enabled": get_reasoner().available(), "version": settings.app_version},
        status_code=200 if ok else 503,
    )


@router.get("/metrics", include_in_schema=False)
async def metrics(authorization: str | None = Header(default=None)) -> Response:
    if not settings.enable_prometheus:
        raise HTTPException(404)
    if settings.metrics_token:
        expected = f"Bearer {settings.metrics_token}"
        if not authorization or not hmac.compare_digest(authorization, expected):
            raise HTTPException(401)
    body, ctype = render_metrics()
    return Response(body, media_type=ctype)
