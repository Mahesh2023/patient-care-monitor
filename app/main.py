"""CARE-MM v3 application entrypoint (`uvicorn app.main:app`)."""
from __future__ import annotations

import asyncio
import contextlib
import mimetypes
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from starlette.staticfiles import StaticFiles
from starlette.types import Scope

from src.care_monitor.config import settings
from src.care_monitor.inference.llm_reasoner import get_reasoner
from src.care_monitor.logging_utils import get_logger

from .api import auth, health, patients, sessions, ws
from .core.db import Base, engine
from .core.kv import kv
from .core.middleware import AppMiddleware
from .services.maintenance import maintenance_loop

log = get_logger(__name__)
STATIC_DIR = Path(__file__).parent / "static"

# Module scripts must be served as JS; WASM as application/wasm (streaming compile).
mimetypes.add_type("text/javascript", ".mjs")
mimetypes.add_type("text/javascript", ".js")
mimetypes.add_type("application/wasm", ".wasm")


class CachedStatic(StaticFiles):
    """Long-lived caching for immutable assets (model, versioned JS/CSS)."""

    async def get_response(self, path: str, scope: Scope):
        resp = await super().get_response(path, scope)
        if resp.status_code == 200:
            immutable = path.startswith("vendor/") or "v=" in scope.get("query_string", b"").decode()
            resp.headers["Cache-Control"] = ("public, max-age=31536000, immutable" if immutable
                                             else "public, max-age=300")
        return resp


@asynccontextmanager
async def lifespan(app: FastAPI):
    problems = settings.validate_for_production()
    if problems:
        raise RuntimeError("Invalid production configuration: " + "; ".join(problems))
    if settings.is_sqlite and not settings.is_production:
        async with engine.begin() as conn:  # dev/test convenience; prod uses Alembic
            await conn.run_sync(Base.metadata.create_all)
    await kv.start()
    task = asyncio.create_task(maintenance_loop())
    log.info("CARE-MM %s started (env=%s, kv=%s, llm=%s)", settings.app_version,
             settings.environment, kv.backend, get_reasoner().available())
    try:
        yield
    finally:
        task.cancel()
        with contextlib.suppress(BaseException):
            await task
        await get_reasoner().aclose()
        await kv.close()
        await engine.dispose()


def create_app() -> FastAPI:
    app = FastAPI(
        title="CARE-MM: Clinically-grounded Multimodal Patient Monitor",
        description=("FACS-grounded, LLM-augmented, privacy-first multimodal distress monitoring "
                     "for non-verbal clinical populations. Not FDA-approved; research / "
                     "educational use only. Face analysis runs on-device in the browser."),
        version=settings.app_version,
        lifespan=lifespan,
        docs_url=None if settings.is_production else "/docs",
        redoc_url=None,
        openapi_url=None if settings.is_production else "/openapi.json",
    )
    if settings.cors_origins:
        app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins,
                           allow_credentials=True, allow_methods=["GET", "POST", "PUT", "DELETE"],
                           allow_headers=["Authorization", "Content-Type"])
    app.add_middleware(AppMiddleware)

    for r in (health.router, auth.router, patients.router, sessions.router, ws.router):
        app.include_router(r)

    app.mount("/static", CachedStatic(directory=STATIC_DIR), name="static")

    @app.get("/", include_in_schema=False)
    async def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html", headers={"Cache-Control": "no-cache"})

    return app


app = create_app()
