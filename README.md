# CARE-MM v3 — Patient Care Monitor

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

## Architecture

```
Browser (caregiver device)
  camera ─► MediaPipe FaceLandmarker (WASM, on-device) ─► blendshapes, head-pose matrix,
  mic    ─► AudioWorklet ─► prosody features (pitch/energy/centroid)    iris landmarks, forehead RGB
                                    │  ~2 KB/s JSON batches every 500 ms (no pixels, no audio)
                                    ▼
Render Web Service (stateless FastAPI, N instances × WEB_CONCURRENCY workers)
  /ws/ingest ─► SessionPipeline: FACS AUs → PSPI pain → rPPG HR → blink/micro-expr →
                dimensional distress (comfort/arousal/pain/engagement) → alert engine
                → async LLM clinical summary (Groq, optional)
  /api/*     ─► auth · patients · sessions/consent · alerts · metrics · GDPR export/delete
  /ws/watch  ─► live alerts for a patient (any device, any instance)
       │                                  │
       ▼                                  ▼
  Render Postgres                    Render Key Value (Redis)
  users, refresh tokens, patients,   rate-limit counters, alert pub/sub,
  monitoring_sessions (consent),     per-user stream caps, maintenance lock
  alerts, session_metrics (1-min)
```

Scientific methods are unchanged from v2 (see [RESEARCH.md](RESEARCH.md)): PSPI (Prkachin & Solomon), rPPG (Poh et al. 2010) — now timestamp-resampled for irregular browser frame rates — blink rate (Soukupová & Čech), MAD-based micro-expressions, Russell circumplex for voice/text.

## Repository layout

```
app/
  main.py              FastAPI app, lifespan, static hosting
  api/                 auth, patients, sessions (consent, tickets, alert ack), ws, health
  core/                db, kv (Redis/in-memory), security (argon2/JWT), middleware, metrics
  services/maintenance.py   retention + session expiry (distributed-lock guarded)
  models.py, schemas.py
  static/              SPA (vanilla JS modules, no build step); vendor/ fetched at build
src/care_monitor/
  pipeline.py          SessionPipeline + wire protocol (single source of truth)
  features/            action_units, pain (PSPI), rppg, blink, micro_expressions, voice, text_sentiment
  inference/           distress_state, alerts, llm_reasoner
  perception/          head_pose, iris_gaze
alembic/               migrations (advisory-locked on Postgres)
scripts/               fetch_assets.py (hash-pinned vendor assets), start.sh (migrate + serve)
loadtest/ingest.js     k6 streaming load test
tests/                 67 unit + integration tests (HTTP + WebSocket)
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
   wires `DATABASE_URL` / `REDIS_URL`, and generates `JWT_SECRET` / `METRICS_TOKEN`.
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
Production refuses to start with a weak/missing `JWT_SECRET`, SQLite, insecure cookies or wildcard CORS.

## Privacy & security model

- Raw video/audio **never leaves the browser**; the server receives numeric features only.
- Explicit per-session consent (24 h TTL), auditable and revocable; revocation stops the stream within 5 s.
- Pseudonymous patients (display name only); client IPs stored as HMAC digests.
- Only per-minute aggregates and alerts are persisted; retention enforced automatically
  (`METRICS_RETENTION_DAYS`, `ALERTS_RETENTION_DAYS`).
- GDPR: per-patient JSON export, patient erasure, full account erasure (FK cascades).
- Strict CSP with all scripts/WASM self-hosted and hash-pinned; HSTS; `X-Frame-Options: DENY`.

## Limitations

- AU estimates come from MediaPipe blendshapes, not certified FACS coding.
- rPPG is sensitive to lighting, motion, skin tone and camera compression — trend use only.
- Voice/text analysis are transparent rule-based models, not clinically validated classifiers.
- Pain expression varies across individuals and cultures; stoic patients may under-express.

## License

Research and educational use. Not for clinical decision-making.
