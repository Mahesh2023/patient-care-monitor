# CARE-MM v3.1 — Patient Care Monitor

**Privacy-first, FACS-grounded multimodal distress monitoring for caregivers of non-verbal patients**
(dementia, ICU, post-stroke aphasia, pediatrics).

> Research / educational use only. Not FDA-approved. Not a medical device.
> Outputs are *behavioural observations*, not emotion detection (Barrett et al., 2019).

## What changed in v3 (production architecture)

| v2 | v3 |
|---|---|
| Browser uploads JPEG frames (~50 KB/s); server runs MediaPipe per frame → ~5 users / CPU core | **Face perception runs in the browser** (MediaPipe Tasks-Vision WASM, self-hosted). Only ~2 KB/s of numeric features are sent → hundreds–thousands of streams / core |
| In-memory sessions & consent (lost on restart, single instance only) | **Postgres** (users, patients, consent audit, alerts, per-minute metrics) + **Redis/Key Value** (rate limits, cross-instance alert fan-out, distributed locks). Stateless web tier — scale horizontally |
| No authentication, CORS `*` | **JWT auth** (argon2id, 15-min access tokens, rotating httpOnly refresh cookies with reuse detection), per-user data isolation |
| Synchronous LLM call on the event loop | Async LLM with per-process concurrency cap, circuit breaker, per-session cooldown |
| Unbounded Prometheus labels (session_id) | Bounded labels, multi-process metrics, structured JSON logs w/ request IDs |
| — | Strict CSP (no third-party scripts), HSTS, rate limiting, body/WS size limits, GDPR export/erasure, retention enforcement, Alembic migrations, CI, k6 load test |

## v3.1: research-driven improvements

| Area | Feature | Evidence / standard |
|---|---|---|
| Signal | **POS heart rate** (Plane-Orthogonal-to-Skin) replaces the green channel | Wang et al. 2017, *IEEE TBME* — cancels illumination changes, less skin-tone dependent |
| Signal | **Signal-quality gating**: SNR (dB), disturbance-index surges, split-half peak consistency — no BPM shown when quality fails | de Haan & Jeanne 2013; CinC 2017 (DI); CinC 2020 (SQI filter: up to 60% accuracy gain) |
| Signal | **Respiratory rate** from head motion + respiratory skin-intensity modulation | Samsung Research 2023 (MAE 1.3 bpm); *Electronics* 2025 14(11):2152 |
| Signal | **Per-patient neutral-face calibration** (first ~20 s, persisted, capped so a grimace cannot be hidden) | Rezaei et al. 2021 *IEEE JBHI*; personalised pain models (EMBC 2021, CVPRW 2017) |
| Signal | **Capture-quality checks** (lighting, face distance, head pose); facial alerts withheld when poor | Smart-alarm signal-quality principle (AAMI) |
| Clinical | **PAINAD**: system suggests breathing / vocalisation / facial items; caregiver completes body language & consolability and records the assessment | Warden, Hurley & Volicer 2003, *JAMDA* |
| Clinical | **Smart alarms**: facial-only pain → CONCERN; corroborated by voice/HR/RR → URGENT; per-patient thresholds & muted keys; respiratory & vocal-distress alerts | AAMI alarm management; AACN Practice Alert; Joint Commission NPSG.06.01.01 |
| Clinical | **Escalation** of unacknowledged URGENT (5 min) / CONCERN (15 min) alerts to every watcher | AAMI: alarm escalation & closed-loop notification |
| Caregiver | **Care-team sharing** (owner / editor / viewer, least privilege) | HIPAA minimum-necessary access |
| Caregiver | **Care events** (medication, repositioning…) with before/after signal comparison | — |
| Caregiver | **Installable PWA** + desktop notifications for alerts while the tab is in the background | Web App Manifest / Service Worker |
| Security | **Audit trail** of every patient-data access, per-patient access log, 6-year retention | HIPAA §164.312(b) audit controls |
| Security | **Password policy**: common-password blocklist, context words, breached-password check (k-anonymity) | OWASP ASVS 5.0 V6.2.4 / NIST SP 800-63B |
| Security | **Soft account lockout** (per account, not just per IP) | OWASP ASVS V6.1.1 / credential-stuffing cheat sheet |
| Security | **TOTP two-factor auth** (RFC 6238), AES-GCM-encrypted secrets, replay protection, one-time recovery codes | NIST SP 800-63B AAL2 |

## Architecture

```
Browser (caregiver device)
  camera ─► MediaPipe FaceLandmarker (WASM, on-device) ─► blendshapes, head-pose matrix,
  mic    ─► AudioWorklet ─► prosody features (pitch/energy/centroid)    iris landmarks, forehead RGB
                                    │  ~2 KB/s JSON batches every 500 ms (no pixels, no audio)
                                    ▼
Render Web Service (stateless FastAPI, N instances × WEB_CONCURRENCY workers)
  /ws/ingest ─► SessionPipeline: baseline-adjusted FACS AUs → PSPI pain → POS heart rate
                (+SQI) → respiratory rate → blink/micro-expr → capture quality →
                dimensional distress → PAINAD suggestions → smart alert engine
                → async LLM clinical summary (Groq, optional)
  /api/*     ─► auth (+TOTP 2FA) · patients · care team · alarm settings · sessions/consent ·
                alerts · metrics · care events (+impact) · PAINAD · audit · GDPR export/delete
  /ws/watch  ─► live + escalated alerts for a patient (any device, any instance)
  background ─► retention (incl. audit) · unacknowledged-alert escalation (distributed locks)
       │                                  │
       ▼                                  ▼
  Render Postgres                    Render Key Value (Redis)
  users, refresh tokens, patients,   rate-limit + lockout counters, alert pub/sub,
  patient_members, sessions,         per-user stream caps, maintenance/escalation locks
  alerts, session_metrics (1-min),
  care_events, painad_assessments,
  audit_events
```

Core scientific methods (see [RESEARCH.md](RESEARCH.md)): PSPI (Prkachin & Solomon), POS rPPG (Wang et al. 2017) with timestamp resampling for irregular browser frame rates, blink rate (Soukupová & Čech), MAD-based micro-expressions, Russell circumplex for voice/text, PAINAD (Warden et al. 2003).

## Repository layout

```
app/
  main.py              FastAPI app, lifespan, static hosting
  api/                 auth (+2FA, audit), patients (settings, baseline, export, access log),
                       care (team, events, impact, PAINAD), sessions (consent, tickets, ack), ws, health
  core/                db, kv (Redis/in-memory), security (argon2/JWT), totp (+AES-GCM), passwords,
                       audit, middleware, metrics
  services/maintenance.py   retention, session expiry, alert escalation (distributed-lock guarded)
  models.py, schemas.py
  static/              SPA (vanilla JS modules, no build step), PWA manifest + service worker;
                       vendor/ fetched at build
src/care_monitor/
  pipeline.py          SessionPipeline + wire protocol (single source of truth)
  features/            action_units, baseline, pain (PSPI), rppg (POS + SQI), respiration, blink,
                       micro_expressions, voice, text_sentiment
  inference/           distress_state, alerts (smart alarms), painad, llm_reasoner
  perception/          head_pose, iris_gaze
alembic/               migrations 0001-0002 (advisory-locked on Postgres)
scripts/               fetch_assets.py (hash-pinned vendor assets), start.sh (migrate + serve)
loadtest/ingest.js     k6 streaming load test
tests/                 94 unit + integration tests (HTTP + WebSocket)
render.yaml            Render Blueprint: web + Postgres + Key Value
```

## Local development

```bash
python -m venv .venv && . .venv/bin/activate         # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
python scripts/fetch_assets.py                        # MediaPipe WASM + model + Chart.js (sha256-verified)
cp .env.example .env                                  # defaults: SQLite, in-memory KV, COOKIE_SECURE=false
python -m alembic upgrade head
uvicorn app.main:app --reload --port 8000             # open http://localhost:8000
```

Camera access requires a secure context: `http://localhost` works; any other host needs HTTPS.

Checks:

```bash
ruff check .
pytest
```

## Deploy to Render (free tier)

1. Push to GitHub (this repo).
2. Render Dashboard → **New → Blueprint** → select the repo → **Apply**.
   This creates `care-mm` (web, Docker), `care-mm-db` (Postgres) and `care-mm-kv` (Key Value),
   wires `DATABASE_URL` / `REDIS_URL`, and generates `JWT_SECRET`, `DATA_ENCRYPTION_KEY` and `METRICS_TOKEN`.
   (Existing Blueprint deploys: click **Sync** so the new `DATA_ENCRYPTION_KEY` is created — production refuses
   to start without it. Never rotate it without re-encrypting stored TOTP secrets.)
3. Optional: set `GROQ_API_KEY` on the `care-mm` service to enable LLM clinical summaries.
4. Open `https://<service>.onrender.com`, create an account, add a patient, start monitoring.

Migrations run automatically on boot (`scripts/start.sh`). Pushes to `main` auto-deploy.

**Free-tier limits:** the web service sleeps after 15 min idle (≈1 min cold start), free Postgres
expires after 30 days, 0.1 CPU / 512 MB. See [docs/SCALING.md](docs/SCALING.md) for the path to 1M+ users.

## Operations

| Endpoint | Purpose |
|---|---|
| `GET /health` | Liveness (Render health check) |
| `GET /ready` | Readiness: DB + KV reachable (503 otherwise) |
| `GET /metrics` | Prometheus; requires `Authorization: Bearer $METRICS_TOKEN` when set |
| `GET /docs` | OpenAPI UI (disabled in production) |

Key environment variables: see [.env.example](.env.example) and `src/care_monitor/config.py`.
Production refuses to start with a weak/missing `JWT_SECRET` or `DATA_ENCRYPTION_KEY`, SQLite, insecure
cookies or wildcard CORS.

## Privacy & security model

- Raw video/audio **never leaves the browser**; the server receives numeric features only.
- Explicit per-session consent (24 h TTL), auditable and revocable; revocation stops the stream within 5 s.
- Pseudonymous patients (display name only); client IPs stored as HMAC digests.
- Only per-minute aggregates and alerts are persisted; retention enforced automatically
  (`METRICS_RETENTION_DAYS`, `ALERTS_RETENTION_DAYS`).
- GDPR: per-patient JSON export, patient erasure, full account erasure (FK cascades).
- Role-based care-team access (owner / editor / viewer); access revocation stops live streams within 5 s.
- Append-only audit trail of patient-data access (survives erasure; pseudonymous ids only), 6-year retention.
- Optional TOTP 2FA; common/breached passwords rejected; per-account soft lockout.
- Strict CSP with all scripts/WASM self-hosted and hash-pinned; HSTS; `X-Frame-Options: DENY`.
- The service worker caches only the static app shell — API responses are never cached.

## Limitations

- AU estimates come from MediaPipe blendshapes, not certified FACS coding.
- rPPG (POS) and respiration are sensitive to lighting, motion, skin tone, camera compression and
  elevated heart rates (npj Digit. Med. 2025) — trend use only; values are hidden when quality gates fail.
- PAINAD items suggested by the system are aids; the score is only valid when a caregiver completes the
  observation (body language and consolability cannot be sensed from a face camera).
- Before/after comparisons around care events are observational, not evidence of treatment effect.
- Voice/text analysis are transparent rule-based models, not clinically validated classifiers.
- Pain expression varies across individuals and cultures; stoic patients may under-express.

## License

Research and educational use. Not for clinical decision-making.
