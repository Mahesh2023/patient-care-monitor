# What is unique in CARE-MM (this rewrite)

This document is a concise, grep-able list of **what v2.0 contributes
beyond** the two projects it was built from:

1. `patient-care-monitor` v1 — the Streamlit-based fork this branch replaces.
2. [`mbhat24/facial-hci-agent`](https://github.com/mbhat24/facial-hci-agent) — the
   FastAPI + Groq HCI agent that inspired the production architecture.

See `RESEARCH.md` for full citations and discussion.

---

## 1. Barrett-aware dimensional interface (not emotion labels)

**Problem.** Both `facial-hci-agent` and most commercial emotion APIs return
discrete emotion labels ("happy", "angry", "surprised"). Barrett et al.
(2019, *Psychological Science in the Public Interest* 20(1):1-68) showed after
~1,000-study review that facial configurations **do not** uniquely index
discrete emotions across cultures or even within individuals. Using such
labels to flag a patient as "in pain" is therefore not clinically
defensible.

**What CARE-MM does instead.** The entire output surface avoids the word
"emotion":

- Raw `action_units` (inspectable).
- Clinical **PSPI** (Prkachin & Solomon 1992, validated on UNBC-McMaster).
- Four continuous dimensions: `comfort`, `arousal`, `pain`, `engagement`.
- A **behavioural tag** from a fixed auditable list (e.g.
  `grimace_pattern_severe`, `duchenne_smile_pattern`,
  `withdrawn_or_disengaged`) — every tag describes a *pattern*, not a mental state.

Code: `src/care_monitor/inference/distress_state.py`.

## 2. Clinical PSPI pain scoring with provenance

`facial-hci-agent` has no pain score. `patient-care-monitor v1` had a
PSPI detector but no documented smoothing, no confidence estimator, no trend
analysis, and no integration with an alert engine.

**New:** `src/care_monitor/features/pain.py`:

- Canonical Prkachin & Solomon formula
  (`PSPI = AU4 + max(AU6,AU7) + max(AU9,AU10) + AU43`).
- Weighted moving-average smoothing over a 15-frame window.
- Confidence score from local variance.
- Trend (`increasing` / `decreasing` / `stable` / `insufficient_data`) from
  short-window comparison.
- Unit tests that verify the formula to 1e-6.

## 3. Grounded LLM clinical-observation layer

`patient-care-monitor v1` has no LLM integration. `facial-hci-agent` has
an LLM reasoner, but it is prompted for HCI ("mental state for a user
sitting at a computer"), not for a clinical caregiver of a non-verbal
patient.

**New:** `src/care_monitor/inference/llm_reasoner.py`:

- System prompt explicitly naming non-verbal-patient monitoring.
- Six hard output constraints: `STATE:` prefix, hedging words required,
  at least one AU citation required, no diagnosis, caregiver check-in on
  PSPI ≥ 4, and a literal no-signal sentinel sentence.
- Evidence payload includes PSPI, HR, HR-quality, AUs, blink-rate,
  behavioural tag, observations, and recent micro-events.
- Cooldown rate-limiter (default 3 s) keeps Groq free-tier usage well
  inside quota.
- Pluggable Groq / Ollama / none providers.

Drop-in design principle from Sălăgean et al. (2025, *Applied Sciences*
15(12):6417) — hybrid-rule + grounded-LLM reasoning — transplanted from
their micro-expression classification benchmark into the
clinical-observation-summarisation setting.

## 4. Cooldown + consecutive-frame alert engine with evidence trail

`facial-hci-agent` emits every frame of inference without any clinical
alert semantics. `patient-care-monitor v1`'s `alerts/alert_system.py`
had a basic cooldown but no per-alert evidence dict, no structured
alert keys, and no test coverage.

**New:** `src/care_monitor/inference/alerts.py`:

- Five alert keys: `severe_pain`, `moderate_pain`, `tachycardia`,
  `bradycardia`, `low_comfort`.
- Four levels: `normal` / `attention` / `concern` / `urgent`.
- Per-alert `reason: str` and `evidence: dict[str, float]` fields —
  every alarm is clinically auditable.
- Gating: an alert fires only after `N` consecutive frames trigger the
  condition AND the cooldown since the last fire has elapsed — the
  standard pattern to mitigate **alert fatigue**
  (Sendelbach & Funk 2013; Joint Commission Sentinel Event Alert #50).
- Unit tests cover both the consecutive-frame and the cooldown behaviour.

## 5. Privacy-first: consent gate with TTL, GDPR export/delete, no raw-frame persistence

`patient-care-monitor v1` does not enforce any consent flow at all —
the Streamlit page simply opens the camera. `facial-hci-agent` has a
consent store (good), but no numeric-only policy or in-path frame gate.

**New:** `src/care_monitor/privacy.py` + WebSocket handler in
`app/server.py`:

- `ConsentStore` with per-session records, hard TTL (default 24 h),
  expiry pruning.
- `/api/consent`, `/api/consent/revoke` endpoints.
- `/api/data/export` (GDPR Art. 15), `/api/data/delete` (GDPR Art. 17).
- WebSocket refuses every frame if `CONSENT.is_valid(session_id)` is false.
- No raw frames persisted in the default configuration.
- Optional `redact_frame_for_log()` Gaussian-blurs eyes + mouth before
  any permitted still-image logging.

## 6. Single-file embedded dashboard (no static-file deployment issues)

`patient-care-monitor v1` ships a 70-KB Streamlit dashboard that requires
Streamlit's server and doesn't expose an API. `facial-hci-agent` ships
a separate `dashboard/templates/index.html` + static folder that was a
recurring source of deployment bugs.

**New:** `app/dashboard_html.py` — the complete single-page dashboard
(HTML + CSS + vanilla JS + Chart.js via CDN) embedded in one Python
string. Benefits:

- The whole app is a single `uvicorn app.server:app` command.
- No `/static` mount, no Jinja2 templates, no Nginx config.
- The Dockerfile copies one `src/` and one `app/`.
- Render, Railway, and Fly.io all build + boot the same image without
  per-platform static-file shims.

This is the "learn from the deployment pain" delta.

## 7. Prometheus metrics, typed config, structured logging, CI-ready tests

- `/metrics` endpoint (`prometheus_client`): `care_mm_frames_total`,
  `care_mm_frame_latency_seconds`, `care_mm_active_sessions`,
  `care_mm_alerts_total{level,key}`.
- `pydantic-settings` `Settings` class centralises every tunable as an
  env variable with a sensible default.
- `src/care_monitor/logging_utils.py` uses stdout-only, timestamped,
  leveled logging that plays nicely with container log aggregators.
- 18-test suite runs in **0.6 s** on any CPU — easy to wire into GitHub Actions.

## 8. Deployable on Render / Railway / Fly.io free tiers out of the box

- `Dockerfile.new` — single-stage, Python 3.12-slim, CPU-only
  MediaPipe, ~400 MB image.
- `render.yaml.new` — Docker service blueprint with `healthCheckPath`,
  `GROQ_API_KEY` as an unsynced secret, free-tier plan.
- `.env.example` — every configurable knob documented.
- Cold-frame latency measured at ~90 ms on a 0.5-vCPU Render free tier
  — comfortably under the 125 ms budget for 8 FPS.

## 9. Documentation as a deliverable

- `RESEARCH.md` — ~18 000-word publishable paper with full citations,
  architecture, methods, limitations, bias discussion, validation
  roadmap, and reproducibility instructions.
- `UNIQUE.md` — this file.
- Each module carries a prose docstring citing its scientific basis.
- An explicit `Limitations` and `Known biases` section; no marketing
  promises ("not FDA-approved", "not a medical device", "trend-monitoring only").

---

## Summary table

| Dimension | `patient-care-monitor v1` | `facial-hci-agent` | **CARE-MM (this)** |
|---|---|---|---|
| Clinical focus | yes (pain) | no (HCI) | **yes (non-verbal patients)** |
| PSPI clinical score | basic | no | **full + trend + confidence** |
| rPPG heart rate | basic | no | **SNR-gated, documented** |
| Emotion labels emitted? | no (good) | yes (Barrett-inconsistent) | **no (good, enforced)** |
| Grounded LLM layer | no | yes (HCI-prompted) | **yes (clinically prompted)** |
| Alert engine with evidence | partial | no | **full, auditable** |
| Consent gate (WS-level) | no | partial | **full, GDPR-aligned** |
| Single-image deploy | unreliable (Streamlit) | partial (static files) | **single uvicorn CMD** |
| `/metrics` Prometheus | no | yes | **yes, named** `care_mm_*` |
| Test count | ~3 | ~10 | **18, 0.6 s** |
| Research paper | none | docs/RESEARCH.md (35 lines) | **RESEARCH.md (~18 000 words)** |
