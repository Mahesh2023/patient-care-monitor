"""Test configuration: isolated SQLite DB, in-memory KV, LLM disabled.

Environment must be set before any `app` / `src` import (settings are read
at import time), hence the module-level assignments.
"""
from __future__ import annotations

import os
import tempfile
import uuid
from pathlib import Path

_DB = Path(tempfile.gettempdir()) / f"care_mm_test_{uuid.uuid4().hex}.db"
os.environ.update({
    "ENVIRONMENT": "test",
    "DATABASE_URL": f"sqlite+aiosqlite:///{_DB.as_posix()}",
    "REDIS_URL": "",
    "JWT_SECRET": "test-secret-" + "x" * 40,
    "COOKIE_SECURE": "false",
    "ENABLE_LLM_REASONING": "false",
    "AUTH_RATE_PER_MINUTE": "100000",
    "API_RATE_PER_MINUTE": "100000",
    "ALERT_CONSECUTIVE_FRAMES": "3",
    "ALERT_COOLDOWN_SECONDS": "0",
    "MAINTENANCE_INTERVAL_SECONDS": "100000",
    "LOG_LEVEL": "WARNING",
})

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture(scope="session")
def app():
    from app.main import app as _app
    return _app


@pytest.fixture()
def client(app):
    with TestClient(app) as c:
        yield c


def _register(client: TestClient, email: str | None = None, password: str = "correct-horse-1") -> dict:
    email = email or f"user-{uuid.uuid4().hex[:10]}@example.com"
    r = client.post("/api/auth/register", json={"email": email, "password": password, "full_name": "T"})
    assert r.status_code == 201, r.text
    return {"email": email, "password": password, "token": r.json()["access_token"]}


@pytest.fixture()
def user(client):
    u = _register(client)
    u["headers"] = {"Authorization": f"Bearer {u['token']}"}
    return u


@pytest.fixture()
def register(client):
    return lambda **kw: _register(client, **kw)


def pytest_sessionfinish(session, exitstatus):
    try:
        _DB.unlink(missing_ok=True)
    except OSError:
        pass
