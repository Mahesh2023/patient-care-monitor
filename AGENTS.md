# AGENTS.md — CARE-MM

## Environment notes (this machine)
- Repo lives under OneDrive; creating/updating a venv inside the repo fails (OSError on file replace).
  Use the venv at `%LOCALAPPDATA%\care-mm-venv` (`& "$env:LOCALAPPDATA\care-mm-venv\Scripts\python" ...`).
- No Docker or Node locally; Docker build is verified in GitHub Actions CI.

## Commands
- Install: `pip install -r requirements-dev.txt`
- Vendor assets (MediaPipe WASM, model, Chart.js; gitignored): `python scripts/fetch_assets.py`
- Lint: `python -m ruff check .`
- Tests: `python -m pytest` (SQLite + in-memory KV, no network)
- Migrations: `python -m alembic upgrade head`; new migration:
  `python -m alembic revision --autogenerate -m "msg"` (point DATABASE_URL at a scratch SQLite file)
- Run: `uvicorn app.main:app --reload` (set `COOKIE_SECURE=false` for http://localhost)

## Conventions
- Wire protocol (browser → server) is defined in `src/care_monitor/pipeline.py`; the server sends
  blendshape order / landmark indices in the `hello` handshake — don't hardcode them in JS.
- `app/static/js/audio.js::extractFeatures` must stay a port of `features/voice.py::extract_features`.
- Pin new dependencies to releases ≥ 7 days old; vendor assets are sha256-pinned in `scripts/fetch_assets.py`.
- Never store raw media; persist only aggregates/alerts. Never label metrics by user/session id.
- Patient-data endpoints must use `deps.patient_access(db, user, patient_id, min_role)` (owner/editor/viewer)
  and call `core.audit.audit(...)` AFTER the business transaction commits (SQLite single-writer).
- Facial alerts are gated by capture quality + calibration; keep new alert keys in `inference/alerts.ALERT_KEYS`
  and the `AlertSettingsIn.muted` Literal in sync.
- Tests: conftest shortens calibration (BASELINE_SECONDS=0.5) and disables HIBP; tests needing alerts on the
  first frames pass `SessionPipeline(baseline={})`.
- Deploy: push to `main` → Render auto-deploys (Blueprint in `render.yaml`).
