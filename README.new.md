# CARE-MM · Clinically-grounded Multimodal Patient Monitor

**FACS-grounded, LLM-augmented, privacy-first multimodal distress monitoring
for non-verbal clinical populations.**

> ⚠ Research / educational use only. **Not a medical device. Not FDA-approved.**
> Never use outputs for medical, legal, disciplinary, or policing decisions.

CARE-MM watches a patient through a webcam and produces, in real time,
a hedged clinical-observation summary suitable for a caregiver of a
**non-verbal** or **communication-impaired** patient (advanced dementia,
ICU-ventilated, pre-verbal pediatric, post-stroke aphasia). It combines:

* **FACS Action Units** from MediaPipe's 478-landmark / 52-blendshape mesh.
* The **Prkachin & Solomon Pain Intensity (PSPI)** score — the validated
  clinical pain surrogate (Lucey et al. 2011, UNBC-McMaster).
* **Remote photoplethysmography (rPPG)** heart rate (Poh, McDuff & Picard 2010),
  SNR-gated so we refuse to emit a BPM when signal is poor.
* **Micro-expression detection** via a MAD-robust AU-spike detector
  (simplified from Sălăgean et al. 2025).
* A **grounded LLM reasoning layer** (Groq Llama-3.3-70B free tier or local
  Ollama) with a clinical prompt that forces hedging, FACS citations,
  and a no-diagnosis rule.
* A **cooldown + consecutive-frame alert engine** with per-alert evidence,
  engineered against alert fatigue (Sendelbach & Funk 2013; Joint
  Commission Sentinel Event Alert #50).
* A **consent-gated, GDPR-aligned privacy layer**: session TTL,
  no raw-frame persistence, export / delete endpoints.

**Crucially — and against the commercial "emotion AI" grain — CARE-MM
never outputs discrete emotion labels.** Per Barrett et al. (2019,
*Psychological Science in the Public Interest* 20(1):1-68), facial
configurations do not uniquely index internal states; every output of
this system is either a muscle-level AU, a validated clinical score,
a continuous dimension, or a named behavioural *pattern*.

For the full scientific narrative see **[`RESEARCH.md`](RESEARCH.md)**
(a ~18 000-word paper with 27 references).
For the novelty delta over prior art see **[`UNIQUE.md`](UNIQUE.md)**.

---

## Architecture

```
Browser (camera + consent)
    │   WebSocket @ ≤ 8 fps, JPEG frames
    ▼
FastAPI  →  CareMonitorAgent (one per session)
    │
    ├─ MediaPipe FaceLandmarker (CPU, 478 lms + 52 blendshapes)
    ├─ AU extraction + amplification + EMA smoothing
    ├─ Head pose / iris gaze / blink-rate / micro-expressions
    ├─ PSPI pain (0-16), trend, confidence
    ├─ rPPG heart rate (forehead green-channel bandpass + FFT, SNR-gated)
    ├─ Dimensional distress state (comfort/arousal/pain/engagement + tag)
    ├─ Cooldown + consecutive-frame alert engine
    └─ LLM reasoner (Groq / Ollama) — hedged, FACS-cited, 1 sentence
        │
        ▼
Dashboard: AU bars · PSPI · HR · comfort/arousal charts · alert feed · LLM summary
```

## Quick start

```bash
git clone https://github.com/Mahesh2023/patient-care-monitor.git
cd patient-care-monitor
git checkout feature/care-mm-rewrite

cp .env.example .env
# optional: paste a free Groq API key from https://console.groq.com/keys
#   GROQ_API_KEY=gsk_...

pip install -r requirements-new.txt
PYTHONPATH=. uvicorn app.server:app --host 0.0.0.0 --port 8000
# open http://localhost:8000
```

Run the 18-test pure-Python suite (no camera needed, < 1 s):

```bash
PYTHONPATH=. pytest tests/test_care_monitor.py -v
```

## Docker

```bash
docker build -f Dockerfile.new -t care-mm:2.0 .
docker run --rm -p 8000:8000 \
  -e GROQ_API_KEY="${GROQ_API_KEY}" \
  care-mm:2.0
```

## Deploy to Render (single service, Docker)

1. Push this branch to GitHub.
2. Render → New → Blueprint → pick this repo.
3. Render reads `render.yaml.new` (rename to `render.yaml` if you prefer).
4. Set `GROQ_API_KEY` in the dashboard (it's configured as `sync: false`).
5. First build takes ~3 min. `/health` returns `{status: "ok"}`.

## API (selected)

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/` | Single-page dashboard |
| GET | `/health` | Liveness + service summary |
| GET | `/metrics` | Prometheus metrics |
| GET | `/docs`, `/openapi.json` | OpenAPI spec |
| POST | `/api/consent` | Grant consent → `{session_id}` |
| POST | `/api/consent/revoke` | Revoke + clean session |
| POST | `/api/data/export` | GDPR Art. 15 — per-session summary |
| POST | `/api/data/delete` | GDPR Art. 17 — erasure |
| WS | `/ws?session_id=...` | JPEG frames → analysis JSON |

Every WebSocket `frame` message yields a `FrameAnalysis` (see
`src/care_monitor/agent.py`) with AUs, head pose, gaze, blink rate,
micro-events, pain, heart rate, distress dimensions, alerts, and
(throttled) LLM summary.

## Ethics & limitations (read before deploying)

* **Not a medical device.** No FDA / CE clearance.
* **Not validated** on any non-verbal clinical cohort. §7.2 of
  `RESEARCH.md` specifies the study protocol that would be required.
* **Skin-tone bias.** rPPG is known to perform worse on darker skin
  (Nowara et al. 2020). MediaPipe's AU priors were learned on a
  predominantly Euro-facial dataset.
* **Confounders.** Eyewear, facial hair, masks, and ventilator tubing
  all degrade AU estimates.
* **Alert fatigue.** The cooldown + consecutive-frame gating is a
  mitigation, not a guarantee. Production deployments must tune
  `ALERT_COOLDOWN_SECONDS` and `ALERT_CONSECUTIVE_FRAMES` to their setting.
* **GDPR.** Facial biometrics are "special category" data (Art. 9).
  A real deployment MUST conduct a DPIA and tie consent to a real
  identity flow — the demo flow in this repo is not sufficient.

## Contributing

* Add a test for any behaviour change (`tests/test_care_monitor.py`).
* Keep the Barrett-aware interface — never add a field that maps a
  face to a discrete emotion label.
* Cite the paper that justifies any threshold you change.

## License

MIT for code. `RESEARCH.md` under CC-BY-4.0. See `LICENSE`.
