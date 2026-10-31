"""HTTP + WebSocket integration tests (TestClient, SQLite, in-memory KV)."""
from __future__ import annotations

import time
import uuid

import pytest
from starlette.websockets import WebSocketDisconnect

from tests.test_pipeline import PAIN, sample


def H(u):
    return {"Authorization": f"Bearer {u['token']}"}


def make_patient(client, u, name="Patient A"):
    r = client.post("/api/patients", json={"display_name": name}, headers=H(u))
    assert r.status_code == 201, r.text
    return r.json()


def start_session(client, u, patient_id):
    r = client.post("/api/sessions", json={"patient_id": patient_id, "consent_confirmed": True}, headers=H(u))
    assert r.status_code == 201, r.text
    return r.json()


# ------------------------------------------------------------- platform
def test_health_ready_and_security_headers(client):
    r = client.get("/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"
    assert "default-src 'self'" in r.headers["content-security-policy"]
    assert r.headers["x-frame-options"] == "DENY"
    assert r.headers["x-request-id"]
    r = client.get("/ready")
    assert r.status_code == 200 and r.json()["checks"] == {"database": True, "kv": True}


def test_index_and_static_served(client):
    r = client.get("/")
    assert r.status_code == 200 and "CARE-MM" in r.text
    r = client.get("/static/js/app.js?v=3.0.0")
    assert r.status_code == 200
    assert "javascript" in r.headers["content-type"]
    assert "immutable" in r.headers["cache-control"]


def test_metrics_exposed_with_route_labels(client):
    client.get("/health")
    r = client.get("/metrics")
    assert r.status_code == 200
    assert 'route="/health"' in r.text


def test_request_too_large_rejected(client):
    r = client.post("/api/auth/login", content=b"x" * 2_000_000, headers={"content-type": "application/json"})
    assert r.status_code == 413


# ------------------------------------------------------------- auth
def test_register_login_me(client, register):
    u = register()
    r = client.post("/api/auth/register", json={"email": u["email"], "password": "another-pass-1"})
    assert r.status_code == 409
    r = client.post("/api/auth/login", json={"email": u["email"].upper(), "password": u["password"]})
    assert r.status_code == 200
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {r.json()['access_token']}"})
    assert me.status_code == 200 and me.json()["email"] == u["email"]
    assert client.post("/api/auth/login", json={"email": u["email"], "password": "wrong-password"}).status_code == 401
    assert client.get("/api/auth/me").status_code == 401
    assert client.get("/api/auth/me", headers={"Authorization": "Bearer garbage"}).status_code == 401


def test_weak_password_rejected(client):
    r = client.post("/api/auth/register", json={"email": "a@example.com", "password": "short"})
    assert r.status_code == 422


def test_refresh_rotation_and_reuse_detection(client, register):
    register()
    old = client.cookies.get("care_rt")
    assert old
    r = client.post("/api/auth/refresh")
    assert r.status_code == 200
    new = client.cookies.get("care_rt")
    assert new and new != old
    # Replaying the rotated token revokes the whole family.
    client.cookies.set("care_rt", old, path="/api/auth")
    assert client.post("/api/auth/refresh").status_code == 401
    client.cookies.clear()
    client.cookies.set("care_rt", new, path="/api/auth")
    assert client.post("/api/auth/refresh").status_code == 401


def test_logout_revokes_refresh(client, register):
    register()
    rt = client.cookies.get("care_rt")
    assert client.post("/api/auth/logout").status_code == 204
    client.cookies.set("care_rt", rt, path="/api/auth")
    assert client.post("/api/auth/refresh").status_code == 401


def test_password_change_invalidates_tokens(client, user):
    r = client.post("/api/auth/password", headers=H(user),
                    json={"current_password": user["password"], "new_password": "brand-new-pass-1"})
    assert r.status_code == 204
    assert client.get("/api/auth/me", headers=H(user)).status_code == 401


def test_auth_rate_limit(client, monkeypatch):
    from app.core.kv import kv
    from src.care_monitor.config import settings
    monkeypatch.setattr(settings, "auth_rate_per_minute", 3)
    kv._counters.clear()  # counters from earlier tests share this minute's window
    codes = [client.post("/api/auth/login", json={"email": "x@example.com", "password": "nope"}).status_code
             for _ in range(5)]
    assert codes[:3] == [401, 401, 401] and 429 in codes[3:]


# ------------------------------------------------------------- patients
def test_patient_crud_and_isolation(client, register):
    a, b = register(), register()
    p = make_patient(client, a)
    assert [x["id"] for x in client.get("/api/patients", headers=H(a)).json()] == [p["id"]]
    assert client.get("/api/patients", headers=H(b)).json() == []
    assert client.get(f"/api/patients/{p['id']}", headers=H(b)).status_code == 404
    r = client.put(f"/api/patients/{p['id']}", json={"display_name": "Renamed"}, headers=H(a))
    assert r.json()["display_name"] == "Renamed"
    assert client.delete(f"/api/patients/{p['id']}", headers=H(b)).status_code == 404
    assert client.delete(f"/api/patients/{p['id']}", headers=H(a)).status_code == 204
    assert client.get(f"/api/patients/{p['id']}", headers=H(a)).status_code == 404


def test_session_requires_consent_and_ownership(client, register):
    a, b = register(), register()
    p = make_patient(client, a)
    r = client.post("/api/sessions", json={"patient_id": p["id"], "consent_confirmed": False}, headers=H(a))
    assert r.status_code == 400
    r = client.post("/api/sessions", json={"patient_id": p["id"], "consent_confirmed": True}, headers=H(b))
    assert r.status_code == 404


# ------------------------------------------------------------- websockets
def test_ws_rejects_bad_ticket(client):
    with client.websocket_connect("/ws/ingest?ticket=nope") as ws:
        assert ws.receive_json()["code"] == "invalid_ticket"
        with pytest.raises(WebSocketDisconnect) as e:
            ws.receive_json()
        assert e.value.code == 4401


def test_ws_ingest_end_to_end_alerts_metrics_ack_export(client, user):
    p = make_patient(client, user)
    s = start_session(client, user, p["id"])
    t0 = int(time.time() * 1000)
    fired = []
    wt = client.post(f"/api/patients/{p['id']}/watch-ticket", headers=H(user)).json()["ws_ticket"]
    with client.websocket_connect(f"/ws/watch?ticket={wt}") as watch:
        assert watch.receive_json()["type"] == "hello"
        with client.websocket_connect(f"{s['ws_path']}?ticket={s['ws_ticket']}") as ws:
            hello = ws.receive_json()
            assert hello["type"] == "hello" and hello["session_id"] == s["session"]["id"]
            ws.send_json({"type": "ping"})
            assert ws.receive_json()["type"] == "pong"
            for b in range(4):
                ws.send_json({"type": "batch",
                              "samples": [sample(t0 + (b * 5 + i) * 100, PAIN) for i in range(5)]})
                msg = ws.receive_json()
                assert msg["type"] == "result"
                fired += msg["data"]["alerts"]
            ws.send_json({"type": "batch", "samples": [{"t": "bad"}]})
            assert ws.receive_json()["code"] == "protocol"
        assert fired, "expected a pain alert"
        pushed = watch.receive_json()
        assert pushed["type"] == "alert" and pushed["patient_id"] == p["id"]

    alerts = client.get(f"/api/patients/{p['id']}/alerts", headers=H(user)).json()
    assert {a["id"] for a in alerts} >= {a["id"] for a in fired}
    r = client.post(f"/api/alerts/{alerts[0]['id']}/ack", headers=H(user))
    assert r.status_code == 200 and r.json()["acknowledged_at"]
    assert client.get(f"/api/patients/{p['id']}/alerts?unacknowledged=true", headers=H(user)).json().__len__() == len(alerts) - 1

    metrics = client.get(f"/api/patients/{p['id']}/metrics", headers=H(user)).json()
    assert metrics and metrics[0]["face_samples"] == 20
    sess = client.get(f"/api/sessions/{s['session']['id']}", headers=H(user)).json()
    assert sess["sample_count"] == 20

    export = client.get(f"/api/patients/{p['id']}/export", headers=H(user)).json()
    assert len(export["sessions"]) == 1 and export["alerts"] and export["metrics"]


def test_ws_refused_after_consent_revoked(client, user):
    p = make_patient(client, user)
    s = start_session(client, user, p["id"])
    assert client.post(f"/api/sessions/{s['session']['id']}/revoke", headers=H(user)).json()["status"] == "revoked"
    with client.websocket_connect(f"/ws/ingest?ticket={s['ws_ticket']}") as ws:
        assert ws.receive_json()["code"] == "consent_required"
    assert client.post(f"/api/sessions/{s['session']['id']}/ticket", headers=H(user)).status_code == 403


def test_ws_ticket_cannot_cross_purpose_or_user(client, register):
    a, b = register(), register()
    p = make_patient(client, a)
    s = start_session(client, a, p["id"])
    with client.websocket_connect(f"/ws/watch?ticket={s['ws_ticket']}") as ws:
        assert ws.receive_json()["code"] == "invalid_ticket"
    assert client.post(f"/api/sessions/{s['session']['id']}/ticket", headers=H(b)).status_code == 404


def test_ws_stream_cap_per_user(client, user, monkeypatch):
    from src.care_monitor.config import settings
    monkeypatch.setattr(settings, "max_active_streams_per_user", 1)
    p = make_patient(client, user)
    s1, s2 = start_session(client, user, p["id"]), start_session(client, user, p["id"])
    with client.websocket_connect(f"/ws/ingest?ticket={s1['ws_ticket']}") as ws1:
        assert ws1.receive_json()["type"] == "hello"
        with client.websocket_connect(f"/ws/ingest?ticket={s2['ws_ticket']}") as ws2:
            assert ws2.receive_json()["code"] == "too_many_streams"


def test_account_deletion_cascades(client, user):
    p = make_patient(client, user)
    start_session(client, user, p["id"])
    assert client.delete("/api/auth/me", headers=H(user)).status_code == 204
    assert client.post("/api/auth/login", json={"email": user["email"], "password": user["password"]}).status_code == 401


def test_maintenance_run_once(client):
    from app.services.maintenance import run_once
    stats = client.portal.call(run_once)  # run on the app's event loop
    assert set(stats) == {"metrics_deleted", "alerts_deleted", "tokens_deleted", "audit_deleted",
                          "sessions_expired"}


def test_unknown_uuid_404(client, user):
    assert client.get(f"/api/patients/{uuid.uuid4()}", headers=H(user)).status_code == 404
    assert client.post(f"/api/alerts/{uuid.uuid4()}/ack", headers=H(user)).status_code == 404
