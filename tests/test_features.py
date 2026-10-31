"""Tests for v3.1 features: security (password policy, lockout, TOTP 2FA, audit),
care team roles, care events + impact, PAINAD assessments, alert settings,
baseline persistence, escalation, PWA endpoints."""
from __future__ import annotations

import time
import uuid
from datetime import UTC, datetime, timedelta

import pytest

from tests.test_api import H, make_patient, start_session
from tests.test_pipeline import PAIN, sample


# ------------------------------------------------------------ password policy
def test_common_and_contextual_passwords_rejected(client):
    for pw in ("1234567890", "qwertyuiop", "password123"):
        r = client.post("/api/auth/register", json={"email": f"{uuid.uuid4().hex[:8]}@example.com", "password": pw})
        assert r.status_code == 422, pw
    r = client.post("/api/auth/register", json={"email": "johnsmith@example.com", "password": "johnsmith-2024!"})
    assert r.status_code == 422 and "email" in r.json()["detail"]


@pytest.mark.asyncio
async def test_breached_password_rejected(monkeypatch):
    from app.core import passwords
    async def fake(_pw): return 42
    monkeypatch.setattr(passwords, "breached_count", fake)
    with pytest.raises(passwords.WeakPassword):
        await passwords.validate_password("a-perfectly-unique-phrase-91", "x@example.com")


# ------------------------------------------------------------ lockout
def test_account_soft_lockout(client, register, monkeypatch):
    from app.core.kv import kv
    from src.care_monitor.config import settings
    u = register()
    monkeypatch.setattr(settings, "login_max_failures", 3)
    kv._counters.clear()
    for _ in range(3):
        assert client.post("/api/auth/login", json={"email": u["email"], "password": "wrong-password-x"}).status_code == 401
    r = client.post("/api/auth/login", json={"email": u["email"], "password": u["password"]})
    assert r.status_code == 429  # locked even with the right password
    kv._counters.clear()
    assert client.post("/api/auth/login", json={"email": u["email"], "password": u["password"]}).status_code == 200


# ------------------------------------------------------------ TOTP
def test_totp_rfc6238_vector_and_encryption():
    import base64

    from app.core import totp
    secret = base64.b32encode(b"12345678901234567890").decode()
    assert totp.code_at(secret, 59) == "287082"           # RFC 6238 Appendix B (6-digit tail)
    assert totp.verify(secret, "287082", t=59) == 1
    assert totp.verify(secret, "287082", last_step=1, t=59) is None   # replay rejected
    enc = totp.encrypt(secret)
    assert enc != secret and totp.decrypt(enc) == secret


def test_totp_2fa_full_flow(client, register):
    from app.core import totp
    u = register()
    r = client.post("/api/auth/2fa/setup", headers=H(u))
    assert r.status_code == 200
    secret = r.json()["secret"]
    assert r.json()["otpauth_uri"].startswith("otpauth://totp/CARE-MM:")
    assert client.post("/api/auth/2fa/enable", json={"code": "000000"}, headers=H(u)).status_code == 400
    r = client.post("/api/auth/2fa/enable", json={"code": totp.code_at(secret)}, headers=H(u))
    assert r.status_code == 200
    codes = r.json()["recovery_codes"]
    assert len(codes) == 8
    # Enabling 2FA revokes existing tokens
    assert client.get("/api/auth/me", headers=H(u)).status_code == 401

    r = client.post("/api/auth/login", json={"email": u["email"], "password": u["password"]})
    assert r.status_code == 200 and r.json()["mfa_required"] is True
    mfa = r.json()["mfa_token"]
    assert client.post("/api/auth/2fa/verify", json={"mfa_token": mfa, "code": "123456"}).status_code == 401
    r = client.post("/api/auth/2fa/verify", json={"mfa_token": mfa, "code": totp.code_at(secret, time.time() + 30)})
    assert r.status_code == 200
    tok = {"Authorization": f"Bearer {r.json()['access_token']}"}
    assert client.get("/api/auth/me", headers=tok).json()["totp_enabled"] is True

    # Recovery code works exactly once
    mfa = client.post("/api/auth/login", json={"email": u["email"], "password": u["password"]}).json()["mfa_token"]
    assert client.post("/api/auth/2fa/verify", json={"mfa_token": mfa, "code": codes[0]}).status_code == 200
    mfa = client.post("/api/auth/login", json={"email": u["email"], "password": u["password"]}).json()["mfa_token"]
    assert client.post("/api/auth/2fa/verify", json={"mfa_token": mfa, "code": codes[0]}).status_code == 401
    r = client.post("/api/auth/2fa/verify", json={"mfa_token": mfa, "code": codes[1]})
    tok = {"Authorization": f"Bearer {r.json()['access_token']}"}

    # MFA token cannot be used as an access token
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {mfa}"}).status_code == 401
    # Disable requires password + second factor
    assert client.post("/api/auth/2fa/disable", json={"password": "nope-nope-nope", "code": codes[2]},
                       headers=tok).status_code == 400
    assert client.post("/api/auth/2fa/disable", json={"password": u["password"], "code": codes[2]},
                       headers=tok).status_code == 204
    r = client.post("/api/auth/login", json={"email": u["email"], "password": u["password"]})
    assert "access_token" in r.json()


# ------------------------------------------------------------ audit
def test_audit_trail_records_access(client, register):
    owner, other = register(), register()
    p = make_patient(client, owner)
    client.get(f"/api/patients/{p['id']}", headers=H(owner))
    client.get(f"/api/patients/{p['id']}/alerts", headers=H(owner))
    client.post("/api/auth/login", json={"email": owner["email"], "password": "wrong-password-x"})
    mine = {e["action"] for e in client.get("/api/auth/audit", headers=H(owner)).json()}
    assert {"auth.register", "patient.create", "patient.read", "alerts.read"} <= mine
    log = client.get(f"/api/patients/{p['id']}/audit", headers=H(owner)).json()
    assert {e["action"] for e in log} >= {"patient.create", "patient.read", "alerts.read"}
    assert client.get(f"/api/patients/{p['id']}/audit", headers=H(other)).status_code == 404


# ------------------------------------------------------------ care team
def test_care_team_roles(client, register):
    owner, viewer, editor, stranger = register(), register(), register(), register()
    p = make_patient(client, owner)
    pid = p["id"]
    assert client.post(f"/api/patients/{pid}/members", json={"email": "nobody@example.com"},
                       headers=H(owner)).status_code == 404
    assert client.post(f"/api/patients/{pid}/members", json={"email": viewer["email"], "role": "viewer"},
                       headers=H(owner)).status_code == 201
    assert client.post(f"/api/patients/{pid}/members", json={"email": editor["email"], "role": "editor"},
                       headers=H(owner)).status_code == 201

    shared = client.get("/api/patients", headers=H(viewer)).json()
    assert [(x["id"], x["role"]) for x in shared] == [(pid, "viewer")]
    members = client.get(f"/api/patients/{pid}/members", headers=H(viewer)).json()
    assert {m["role"] for m in members} == {"owner", "viewer", "editor"}

    # viewer: read-only
    assert client.get(f"/api/patients/{pid}/alerts", headers=H(viewer)).status_code == 200
    assert client.post("/api/sessions", json={"patient_id": pid, "consent_confirmed": True},
                       headers=H(viewer)).status_code == 403
    assert client.post(f"/api/patients/{pid}/events", json={"kind": "medication"}, headers=H(viewer)).status_code == 403
    assert client.put(f"/api/patients/{pid}", json={"display_name": "x"}, headers=H(viewer)).status_code == 403
    assert client.post(f"/api/patients/{pid}/watch-ticket", headers=H(viewer)).status_code == 200
    # editor: can monitor and log care, cannot manage team/settings/export
    s = start_session(client, editor, pid)
    assert client.post(f"/api/patients/{pid}/events", json={"kind": "repositioning"}, headers=H(editor)).status_code == 201
    assert client.post(f"/api/patients/{pid}/members", json={"email": stranger["email"]},
                       headers=H(editor)).status_code == 403
    assert client.get(f"/api/patients/{pid}/export", headers=H(editor)).status_code == 403
    # stranger: no existence disclosure
    assert client.get(f"/api/patients/{pid}", headers=H(stranger)).status_code == 404

    # Removing the editor stops their live stream on the next flush and blocks reconnects
    with client.websocket_connect(f"/ws/ingest?ticket={s['ws_ticket']}") as ws:
        assert ws.receive_json()["type"] == "hello"
    assert client.delete(f"/api/patients/{pid}/members/{_uid(client, editor)}", headers=H(owner)).status_code == 204
    assert client.post(f"/api/sessions/{s['session']['id']}/ticket", headers=H(editor)).status_code == 403
    # viewer can leave
    assert client.delete(f"/api/patients/{pid}/members/{_uid(client, viewer)}", headers=H(viewer)).status_code == 204
    assert client.get("/api/patients", headers=H(viewer)).json() == []


def _uid(client, u) -> str:
    return client.get("/api/auth/me", headers=H(u)).json()["id"]


# ------------------------------------------------------------ care events + impact
def test_care_events_and_impact(client, user):
    p = make_patient(client, user)
    pid = uuid.UUID(p["id"])
    s = start_session(client, user, p["id"])
    t = datetime.now(UTC) - timedelta(minutes=30)
    r = client.post(f"/api/patients/{pid}/events", json={"kind": "medication", "note": "paracetamol 1g",
                                                         "occurred_at": t.isoformat()}, headers=H(user))
    assert r.status_code == 201
    ev = r.json()
    assert client.post(f"/api/patients/{pid}/events", json={"kind": "bogus"}, headers=H(user)).status_code == 422
    assert client.post(f"/api/patients/{pid}/events",
                       json={"kind": "meal", "occurred_at": (datetime.now(UTC) - timedelta(days=30)).isoformat()},
                       headers=H(user)).status_code == 422

    async def seed():
        from app.core.db import SessionLocal
        from app.models import SessionMetric
        async with SessionLocal() as db:
            for i in range(10):
                before = i < 5
                db.add(SessionMetric(session_id=uuid.UUID(s["session"]["id"]), patient_id=pid,
                                     bucket_start=t + timedelta(minutes=(i - 5) * 3),
                                     samples=600, face_samples=600, avg_pspi=6.0 if before else 2.0,
                                     max_pspi=9.0 if before else 3.0, avg_comfort=0.3 if before else 0.7,
                                     avg_hr=95.0 if before else 80.0, avg_rr=None, alerts=1 if before else 0))
            await db.commit()
    client.portal.call(seed)

    events = client.get(f"/api/patients/{pid}/events", headers=H(user)).json()
    assert [e["id"] for e in events] == [ev["id"]]
    imp = client.get(f"/api/patients/{pid}/events/{ev['id']}/impact", headers=H(user)).json()
    assert imp["before"]["avg_pspi"] == pytest.approx(6.0) and imp["after"]["avg_pspi"] == pytest.approx(2.0)
    assert imp["delta_avg_pspi"] == pytest.approx(-4.0) and imp["delta_avg_comfort"] == pytest.approx(0.4)
    assert imp["before"]["alerts"] == 5 and "not evidence" in imp["note"]


# ------------------------------------------------------------ PAINAD
def test_painad_assessments(client, user):
    p = make_patient(client, user)
    body = {"breathing": 1, "negative_vocalization": 2, "facial_expression": 2, "body_language": 1,
            "consolability": 1, "auto_items": {"breathing": 1, "negative_vocalization": None, "facial_expression": 2}}
    r = client.post(f"/api/patients/{p['id']}/assessments", json=body, headers=H(user))
    assert r.status_code == 201 and r.json()["total"] == 7 and r.json()["interpretation"] == "severe"
    assert client.post(f"/api/patients/{p['id']}/assessments", json={**body, "breathing": 3},
                       headers=H(user)).status_code == 422
    rows = client.get(f"/api/patients/{p['id']}/assessments", headers=H(user)).json()
    assert len(rows) == 1 and rows[0]["auto_items"]["facial_expression"] == 2


# ------------------------------------------------------------ alert settings
def test_alert_settings_validation_and_access(client, register):
    owner, viewer = register(), register()
    p = make_patient(client, owner)
    client.post(f"/api/patients/{p['id']}/members", json={"email": viewer["email"]}, headers=H(owner))
    d = client.get(f"/api/patients/{p['id']}/alert-settings", headers=H(owner)).json()
    assert d["hr_high"] == 100 and d["muted"] == []
    bad = {**d, "pspi_severe": 3.0, "pspi_moderate": 4.0}
    assert client.put(f"/api/patients/{p['id']}/alert-settings", json=bad, headers=H(owner)).status_code == 422
    good = {**d, "hr_high": 110, "muted": ["low_comfort"]}
    assert client.put(f"/api/patients/{p['id']}/alert-settings", json=good, headers=H(viewer)).status_code == 403
    r = client.put(f"/api/patients/{p['id']}/alert-settings", json=good, headers=H(owner))
    assert r.status_code == 200
    assert client.get(f"/api/patients/{p['id']}/alert-settings", headers=H(viewer)).json()["hr_high"] == 110


# ------------------------------------------------------------ calibration persistence
def test_baseline_calibrated_persisted_and_reset(client, user):
    p = make_patient(client, user)
    s = start_session(client, user, p["id"])
    t0 = int(time.time() * 1000)
    states = []
    with client.websocket_connect(f"/ws/ingest?ticket={s['ws_ticket']}") as ws:
        ws.receive_json()
        for b in range(4):
            # 5 samples / 250 ms per batch; calibration needs >= 0.5 s and >= 5 samples
            ws.send_json({"type": "batch", "samples": [sample(t0 + (b * 5 + i) * 50, {}) for i in range(5)]})
            states.append(ws.receive_json()["data"]["calibration"]["state"])
        ws.send_json({"type": "recalibrate"})
        assert ws.receive_json()["type"] == "recalibrating"
    assert states[0] == "calibrating" and states[-1] == "calibrated"
    assert client.get(f"/api/patients/{p['id']}", headers=H(user)).json()["baseline_updated_at"]
    assert client.delete(f"/api/patients/{p['id']}/baseline", headers=H(user)).status_code == 204
    assert client.get(f"/api/patients/{p['id']}", headers=H(user)).json()["baseline_updated_at"] is None


# ------------------------------------------------------------ escalation
def test_unacknowledged_urgent_alert_escalates_once(client, user):
    p = make_patient(client, user)
    s = start_session(client, user, p["id"])
    aid = uuid.uuid4()

    async def seed():
        from app.core.db import SessionLocal
        from app.models import Alert
        async with SessionLocal() as db:
            db.add(Alert(id=aid, session_id=uuid.UUID(s["session"]["id"]), patient_id=uuid.UUID(p["id"]),
                         key="severe_pain", level="urgent", reason="test", evidence={},
                         created_at=datetime.now(UTC) - timedelta(minutes=10)))
            await db.commit()
    client.portal.call(seed)
    from app.services.maintenance import escalate_once
    wt = client.post(f"/api/patients/{p['id']}/watch-ticket", headers=H(user)).json()["ws_ticket"]
    with client.websocket_connect(f"/ws/watch?ticket={wt}") as watch:
        watch.receive_json()
        assert client.portal.call(escalate_once) >= 1
        msg = watch.receive_json()
        assert msg["escalated"] is True and msg["id"] == str(aid) and "UNACKNOWLEDGED" in msg["reason"]
    assert client.portal.call(escalate_once) == 0  # only once
    a = client.get(f"/api/patients/{p['id']}/alerts", headers=H(user)).json()[0]
    assert a["escalated_at"]


# ------------------------------------------------------------ streaming result shape
def test_stream_result_has_new_clinical_fields(client, user):
    p = make_patient(client, user)
    s = start_session(client, user, p["id"])
    t0 = int(time.time() * 1000)
    with client.websocket_connect(f"/ws/ingest?ticket={s['ws_ticket']}") as ws:
        ws.receive_json()
        ws.send_json({"type": "batch", "samples": [sample(t0 + i * 100, PAIN) for i in range(5)]})
        d = ws.receive_json()["data"]
    assert {"calibration", "quality", "painad", "respiration"} <= set(d)
    assert d["painad"]["requires_caregiver"] == ["body_language", "consolability"]
    assert d["quality"]["lighting"] == "ok"


# ------------------------------------------------------------ PWA
def test_pwa_endpoints(client):
    r = client.get("/sw.js")
    assert r.status_code == 200 and "javascript" in r.headers["content-type"]
    assert r.headers["service-worker-allowed"] == "/" and "no-cache" in r.headers["cache-control"]
    m = client.get("/manifest.webmanifest")
    assert m.status_code == 200 and m.json()["display"] == "standalone"
    assert client.get("/static/icons/icon-512.png").status_code == 200
