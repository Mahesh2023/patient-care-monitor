"""Pure-ASGI middleware (no BaseHTTPMiddleware overhead; WS passes through).

* X-Request-ID propagation + contextvar for log correlation
* Security headers (CSP, HSTS, frame/referrer/permissions policies)
* Request body size cap
* Access log + Prometheus HTTP metrics
"""
from __future__ import annotations

import time
import uuid

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from src.care_monitor.config import settings
from src.care_monitor.logging_utils import get_logger, request_id_var

from .metrics import HTTP_LATENCY, HTTP_REQUESTS

log = get_logger("care_mm.access")

# All assets (incl. MediaPipe WASM + model) are self-hosted: no third-party origins.
CSP = "; ".join([
    "default-src 'self'",
    "script-src 'self' 'wasm-unsafe-eval'",
    "worker-src 'self' blob:",
    "connect-src 'self'",
    "img-src 'self' data: blob:",
    "media-src 'self' blob: mediastream:",
    "style-src 'self' 'unsafe-inline'",
    "font-src 'self'",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
])


def _security_headers() -> list[tuple[bytes, bytes]]:
    h = [
        (b"content-security-policy", CSP.encode()),
        (b"x-content-type-options", b"nosniff"),
        (b"x-frame-options", b"DENY"),
        (b"referrer-policy", b"no-referrer"),
        (b"permissions-policy", b"camera=(self), microphone=(self), geolocation=()"),
        (b"cross-origin-opener-policy", b"same-origin"),
    ]
    if settings.is_production:
        h.append((b"strict-transport-security", b"max-age=63072000; includeSubDomains"))
    return h


class AppMiddleware:
    def __init__(self, app: ASGIApp, max_body_bytes: int = 1_000_000) -> None:
        self.app = app
        self.max_body = max_body_bytes
        self.sec_headers = _security_headers()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            return await self.app(scope, receive, send)

        headers = dict(scope.get("headers") or [])
        rid = headers.get(b"x-request-id", b"").decode()[:64] or uuid.uuid4().hex
        token = request_id_var.set(rid)
        try:
            if scope["type"] == "websocket":
                return await self.app(scope, receive, send)
            await self._http(scope, receive, send, headers, rid)
        finally:
            request_id_var.reset(token)

    async def _http(self, scope: Scope, receive: Receive, send: Send, headers: dict, rid: str) -> None:
        cl = headers.get(b"content-length")
        if cl and cl.isdigit() and int(cl) > self.max_body:
            await send({"type": "http.response.start", "status": 413,
                        "headers": [(b"content-type", b"application/json")]})
            await send({"type": "http.response.body", "body": b'{"detail":"request too large"}'})
            return

        received = 0

        async def limited_receive() -> Message:
            nonlocal received
            msg = await receive()
            if msg["type"] == "http.request":
                received += len(msg.get("body", b""))
                if received > self.max_body:
                    raise ValueError("request body too large")
            return msg

        status = 500
        start = time.perf_counter()

        async def send_wrapper(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                hdrs = list(message.get("headers", []))
                hdrs.append((b"x-request-id", rid.encode()))
                hdrs.extend(self.sec_headers)
                message["headers"] = hdrs
            await send(message)

        try:
            await self.app(scope, limited_receive, send_wrapper)
        finally:
            dt = time.perf_counter() - start
            route = scope.get("route")
            path = getattr(route, "path", None) or ("/static" if scope["path"].startswith("/static") else "unmatched")
            HTTP_REQUESTS.labels(scope["method"], path, str(status)).inc()
            HTTP_LATENCY.labels(path).observe(dt)
            if path not in ("/health", "/metrics"):
                log.info("%s %s %s %.1fms", scope["method"], path, status, dt * 1000)
