# CARE-MM: A FACS-Grounded, LLM-Augmented, Privacy-Preserving Multimodal Remote Distress Monitor for Non-Verbal Clinical Populations

*Manuscript prepared in the style of the IEEE Journal of Biomedical and Health Informatics (J-BHI). Preprint; not peer-reviewed. Clinical claims in §V are **software** measurements; §VI defines the clinical validation protocol that must be completed before any patient-facing use.*

---

**A. Mahesh Bhat** — *Independent Research Software Engineering*
Repository: `https://github.com/Mahesh2023/patient-care-monitor` (branch `feature/care-mm-rewrite`)
Version: `care-mm v2.0.0`

---

## Abstract

**Background.** Approximately 40-80% of patients in advanced-dementia care cannot self-report pain reliably [1], and the same holds for ICU-ventilated, pre-verbal pediatric, and post-stroke-aphasia populations. Observer-rated scales (PAINAD, CPOT, NCCPC, FLACC) close this gap only partially: they are discrete, nurse-time-intensive, and noisy. Commercial "emotion AI" systems have been systematically refuted by Barrett *et al.* (2019) [2] as clinically valid pain indicators, and existing research-grade systems report strong UNBC-McMaster or BioVid benchmark numbers [3]–[5] without providing an auditable, deployable, clinician-in-the-loop artefact.

**Methods.** We present **CARE-MM** (Clinically-grounded, Accessible Remote Evaluation — Multimodal Monitor), a real-time, browser-based monitor combining (i) MediaPipe-derived Facial Action Units, (ii) the clinically validated Prkachin–Solomon Pain Intensity (PSPI) score [6], (iii) forehead-green-channel remote photoplethysmography [7], (iv) a Median-Absolute-Deviation-robust micro-expression detector inspired by Sălăgean *et al.* (2025) [8], (v) a **grounded** Large-Language-Model reasoning layer (Groq Llama-3.3-70B or local Ollama) with six hard output constraints, and (vi) a **cooldown + consecutive-frame alert engine** engineered against alert fatigue [9], [10]. The entire inference surface reports **dimensional** states (comfort, arousal, pain, engagement) and named behavioural patterns rather than discrete emotion labels.

**Deployment artefact.** A single ≈ 400 MB Docker image running on CPU-only free-tier (Render/Railway/Fly.io) infrastructure; a consent-gated WebSocket refuses every frame from sessions without a valid 24-hour-TTL consent record; no raw frame is persisted; GDPR Art. 15 / 17 endpoints are implemented.

**Software evaluation.** An 18-test pure-Python suite validating every inference rule passes in 0.6 s. Per-frame latency measured at ≈ 90 ms on a 0.5-vCPU free-tier container.

**Contributions.** (C1) A Barrett-compliant dimensional interface with zero emotion labels. (C2) A grounded clinical LLM reasoner with enforced hedging + FACS citations. (C3) An auditable, evidence-carrying alert engine with cooldown + consecutive-frame gating. (C4) A single-binary, consent-gated, CPU-only deployable architecture. No benchmark accuracy is quoted; §VI defines the clinical studies (PSPI on UNBC-McMaster, PAINAD concordance on dementia cohort, Fitzpatrick I-VI fairness audit, alert-fatigue measurement, and LLM-hallucination audit) required before any clinical deployment.

**Index Terms** — affective computing, facial action coding system, Prkachin–Solomon Pain Intensity, remote photoplethysmography, large language models, clinical decision support, non-verbal pain assessment, alert fatigue, privacy-preserving machine learning, GDPR.

---

## I. Introduction

### A. The non-verbal-pain gap

Pain is the most prevalent distressing symptom for hospitalised and end-of-life patients. The gold standard is self-report on a Numeric Rating Scale or Visual Analogue Scale. Yet an estimated **40–80%** of residents in advanced-dementia care cannot self-report reliably [1]; the same holds for ICU patients under mechanical ventilation, pre-verbal infants, and post-stroke aphasia. Observer-rated instruments — **PAINAD** [11], **NCCPC** [12], **CPOT** [13], **FLACC** — are the fallback, but they are discrete, nurse-time-intensive, and known to under-detect distress in multi-patient wards [14]. A **continuous, low-cost, low-burden** screening tool that flags probable distress for clinician review would close a documented clinical gap, especially in long-term-care settings where nurse-to-patient ratios make frequent manual pain assessment impractical.

Facial expression is a physiologically privileged route: it survives cognitive impairment, partial intubation, and language loss. The Facial Action Coding System (FACS) [15] and the derived Prkachin–Solomon Pain Intensity score [6], validated on the UNBC-McMaster Shoulder Pain Archive [3], give a principled, muscle-level vocabulary for pain expression with three decades of clinical pedigree.

### B. Why commercial "emotion AI" is not a solution

Barrett *et al.* (2019) reviewed ~1,000 studies in a multi-disciplinary *Psychological Science in the Public Interest* consensus review [2] and concluded that facial-configuration-to-emotion mapping is many-to-many across cultures, situations, and even individuals. A model trained to classify a face into {happy, sad, angry, …} is therefore not a valid pain sensor, regardless of benchmark accuracy. The clinically defensible route is to stay at the observable-behaviour layer: report the muscles (AUs) and the documented pattern (grimace, Duchenne smile, withdrawal) and hand the inference to a trained clinician.

### C. Why modern research systems are not (yet) clinical products

Recent deep-learning systems achieve impressive benchmark accuracy. Gkikas *et al.* (2024) [5] report 82.74 % binary accuracy and 39.77 % multi-level accuracy on BioVid using a video + ECG transformer (9.62 M parameters, LOSO cross-validation). Cen *et al.* (2025) [4] propose ConvNeXt+LSTM spatio-temporal pain detection on the PEMF database. A 2023 comprehensive multimodal study [16] fuses EDA, ECG, sEMG, video, and RSP on BioVid. None of these systems, however, ship:

1. a *browser-deployable* monitor a caregiver can open in a mobile tab;
2. an *auditable* inference pipeline where every score traces to specific AUs;
3. a *clinical-reasoning* layer producing hedged, evidence-citing natural-language summaries;
4. an *alert-fatigue-aware* notification engine with documented gating;
5. a *privacy-first* consent + TTL + GDPR gate.

CARE-MM fills precisely this gap — trading some benchmark accuracy for deployability, auditability, and clinical-safety engineering.

### D. Why adding an LLM is *not* the usual bad idea

LLMs hallucinate. A 2025 clinical-summarisation study of 12,999 clinician-annotated LLM-generated sentences across 18 experimental configurations [17] measured a **1.47 % major-hallucination rate and 3.45 % omission rate**, with iterative prompt engineering able to push major errors below previously reported human note-taking rates. The lesson is not "avoid LLMs" but *ground them in auditable evidence and constrain their output format.*

CARE-MM's LLM reasoner is **grounded** in the rule-based AU / PSPI / rPPG / blink-rate / tag outputs (the LLM never sees a raw frame); its system prompt imposes six hard constraints (hedging words, AU citations, no-diagnosis clause, `STATE:` prefix, caregiver-check-in trigger, sentinel no-signal sentence); any non-compliant output is auto-patched on ingress. This mirrors the grounding-beats-hallucination strategy of Sălăgean *et al.* (2025) [8], who pushed CASME II micro-expression accuracy to **93.3 %** by giving GPT the AU evidence instead of the raw frame.

### E. Contributions

1. **C1** — Barrett-compliant **dimensional interface**: every output channel of `FrameAnalysis` is either a raw AU, a validated clinical score (PSPI), a [0,1] dimension (comfort, arousal, pain, engagement), or a behavioural-pattern tag from the fixed 11-member vocabulary in Table III. The word "emotion" appears in the source only in docstrings and system-prompt negations (where we explicitly forbid emotion claims); **it is never a value** of any `FrameAnalysis` field.
2. **C2** — Grounded **clinical LLM reasoner** with versioned system prompt, six hard constraints, and 3-second rate limit.
3. **C3** — Auditable **alert engine** with cooldown + consecutive-frame gating, `reason` string, `evidence` dict, four severity levels, and unit-test coverage.
4. **C4** — Consent-gated **single-binary deployment** on CPU-only free-tier infrastructure with no raw-frame persistence, GDPR Art. 15/17 endpoints, Prometheus metrics, and an embedded dashboard eliminating static-file serving.

Sections II-IV cover related work, architecture, and methods. §V evaluates the system as *software*. §VI defines the *clinical* validation protocol. §VII discusses limitations, biases, and ethics.

---

## II. Related Work

### A. Pain from the face

**FACS and PSPI.** Ekman & Friesen [15] decomposed facial expression into ~46 discrete muscle Action Units. Prkachin (1992) [18] and Prkachin & Solomon (2008) [6] isolated the AUs most sensitive to pain — AU4, AU6/AU7, AU9/AU10, AU43 — and defined

$$
\text{PSPI} = AU_{4} + \max(AU_{6}, AU_{7}) + \max(AU_{9}, AU_{10}) + AU_{43}
$$

each AU on the FACS A-E 0-5 intensity scale. PSPI was validated on the UNBC-McMaster Shoulder Pain Archive (200 videos, 48,398 FACS-coded frames, 129 participants) [3]. Classical learned classifiers on UNBC-McMaster report frame-level accuracies around 87 % [19]. Werner *et al.* (2017) [20] is the canonical reference for automatic pain assessment with facial activity descriptors.

**Recent deep-learning systems (2024-2025).** Cen *et al.* (2025) [4] propose ConvNeXt+LSTM and STGCN+LSTM on PEMF for binary pain classification. Gkikas *et al.* (2024) [5] fuse facial video with ECG-derived heart rate in a vision-transformer + Temporal-Module pipeline (9.62 M parameters, LOSO on BioVid, 82.74 % binary / 39.77 % multi-level). A 2024 systematic review [21] surveys the whole sub-field. Benavent-Lledo *et al.* (2023) [16] audit multimodal fusion across video, EDA, ECG, sEMG, and respiration on BioVid and explicitly call for approaches "aligned with clinical interpretability."

**Production FACS coders.** OpenFace 2.0 [22] and the Python `py-feat` toolbox [23] are the established FACS extractors. Google's MediaPipe FaceLandmarker [24] exposes 478 3-D landmarks and 52 ARKit-compatible blendshape coefficients at ≥ 30 fps on CPU; its blendshape space maps approximately onto ~20 AUs [25] and has enabled a wave of browser-deployable affective-computing apps.

### B. Observer-rated non-verbal pain scales

PAINAD [11] (5 items: breathing, negative vocalisation, facial expression, body language, consolability, each 0-2) is the most widely used instrument for advanced dementia and has been multi-center validated [26]. NCCPC [12] is the analogue for non-verbal intellectual disability. CPOT [13] is the ICU-ventilated analogue. FLACC and N-PASS are the pediatric variants. CARE-MM's observation list (e.g. `brow_furrow (AU4)`, `lip_corner_depressor (AU15)`, `gaze_averted`) is *designed* to map onto PAINAD and CPOT line items so a clinician can cross-check the automated flag against the scale they already know. §VI.B operationalises this mapping.

### C. Remote photoplethysmography

rPPG (Verkruysse *et al.* 2008 [27]; Poh *et al.* 2010 [7]) recovers the cardiac pulse from minute skin-colour changes in a facial ROI. Modern algorithms include CHROM [28], POS [29], DeepPhys [30], and PhysNet.

**Demographic bias.** Nowara *et al.* (2020) [31] meta-analysed skin-tone and gender impact. Bondarenko *et al.* (2025) [32], a PRISMA audit of 100 rPPG studies, reports that public datasets (UBFC-rPPG 26 %, PURE 17 %, COHFACE 11 %) are skewed toward lighter skin tones and cites Dasari *et al.*: traditional chrominance-based rPPG has mean absolute error **5.2 bpm on Fitzpatrick I-III subjects that degrades to 14.1 bpm on Fitzpatrick V-VI** (p < 0.01); deep methods reduce but do not eliminate the gap (6.0 → 9.5 bpm). CARE-MM therefore SNR-gates every rPPG output and refuses to emit a BPM when signal quality is poor; we document this bias in §VII.

### D. Micro-expressions and LLM grounding

Sălăgean *et al.* (2025) [8] demonstrated that a hybrid of AU-activation rules and GPT reasoning *grounded in the AU evidence* reaches **93.3 %** accuracy on CASME II [33] — beating pure rule-based or pure-LLM baselines. The interpretability gain is that the LLM is *not* operating on pixels; every generation is conditioned on the extracted AU vector, enabling post-hoc audit.

A parallel line of work measures LLM hallucination in clinical settings. Asgari *et al.* (2025) [17] built the **CREOLA** framework — error taxonomy, iterative experimentation, clinical-safety grading — and reported 1.47 % hallucination / 3.45 % omission rates on 12,999 clinician-annotated LLM-generated sentences across 18 prompt configurations. Major errors were pushed below human note-taking rates through prompt iteration. The lesson CARE-MM internalises: *ground the LLM, constrain its output, log every generation for audit.*

### E. Alert fatigue

Sendelbach & Funk (2013) [9] and Joint Commission Sentinel Event Alert #50 (2013) [10] established **alert fatigue** as a patient-safety-grade risk. 2024-2025 ICU-alarm-management studies [34]–[37] report that typical ICUs generate hundreds of alarms per patient per day with high false-positive rates, causing nurse desensitisation. The standard mitigation is (a) require the trigger condition for *N* consecutive frames before firing, and (b) impose a *cooldown* after each fire. CARE-MM implements exactly this pattern (§IV.G) with test coverage of both gates.

### F. Comparison with prior open-source art

**Table I. CARE-MM vs. the two direct open-source ancestors.**

| Dimension | `patient-care-monitor` v1 | `facial-hci-agent` (mbhat24) | **CARE-MM (this)** |
|-----------|:---:|:---:|:---:|
| Clinical target (non-verbal patients) | yes | no (generic HCI) | **yes** |
| Emits discrete emotion labels | no | **yes (contra [2])** | no |
| PSPI with trend + confidence | basic | no | **full** |
| rPPG HR with SNR gate | basic | no | **yes** |
| Micro-expression spike detector | no | yes | **yes (MAD-robust)** |
| Grounded LLM (clinical prompt) | no | yes (HCI-prompted) | **yes (clinical)** |
| Cooldown + consecutive alert engine | partial | no | **full, test-covered** |
| Per-alert `evidence` dict | no | no | **yes** |
| Consent gate in the WebSocket | no | partial | **yes (hard refuse)** |
| GDPR Art. 15/17 endpoints | no | yes | **yes** |
| Raw-frame persistence default | unclear | disabled | **disabled + redaction helper** |
| Prometheus `/metrics` | no | yes | **yes, `care_mm_*`** |
| Single `uvicorn` deploy command | no (Streamlit) | partial | **yes (embedded HTML)** |
| Test coverage of inference rules | ~3 | ~10 (non-clinical) | **18 (clinical), 0.6 s** |
| Accompanying research paper | none | 35-line README | **this document** |

---

## III. System Architecture

### A. Pipeline

The system is a single FastAPI process with per-session `CareMonitorAgent` instances. A browser client POSTs `/api/consent`, opens a `WebSocket /ws?session_id=...`, and streams JPEG-encoded frames at ≤ 8 fps (server rate-limited to 15 fps). Each frame yields a `FrameAnalysis` JSON record.

```
Browser (camera + consent modal)
    │   WebSocket JPEG @ ≤ 8 fps
    ▼
FastAPI + Prometheus  ──► SessionRegistry (per-session agents, GC every 60 s)
                                    │
                                    ▼
                          ┌──────────────────────┐
                          │  CareMonitorAgent     │
                          └──────────┬────────────┘
                                     │
    ┌────────────┬───────────────────┼────────────────────┬─────────────┐
    ▼            ▼                   ▼                    ▼             ▼
MediaPipe   AU extraction +       Blink +            rPPG (forehead   Head pose,
FaceLmkr    bilateral avg         micro-expr         green bandpass   iris gaze,
(CPU, 478   + amplification       (MAD-robust)       + FFT, SNR-gated) eye state
lms+52 BS)  + EMA smoothing       [Sălăgean '25]    [Poh '10]
    │            │                   │                    │             │
    └────────────┴───────────────────┼────────────────────┴─────────────┘
                                     ▼
                ┌──────────────────────────────────────────┐
                │ PSPI pain + distress dimensions +        │
                │ behavioural tag + alert engine           │
                └──────────────────┬───────────────────────┘
                                   ▼
                ┌──────────────────────────────────────────┐
                │ LLM reasoner (Groq/Ollama, grounded)     │
                │ one hedged, FACS-citing sentence         │
                └──────────────────┬───────────────────────┘
                                   ▼
                FrameAnalysis JSON → WebSocket → dashboard
```

### B. Per-frame data contract

Every analysed frame produces a `FrameAnalysis` record (defined in `src/care_monitor/agent.py`) with the fields in Table II.

**Table II. `FrameAnalysis` per-frame record.**

| Field | Type | Source |
|-------|------|--------|
| `face_detected` | bool | MediaPipe |
| `action_units` | dict[str, float ∈ [0,1]] | blendshape → AU → EMA smoother |
| `active_aus` | list[str] | AUs > 0.15 |
| `head_pose` | {pitch, yaw, roll} deg | 4×4 transformation matrix |
| `gaze` | {h_ratio, v_ratio, averted} | iris / eye-corner geometry |
| `blink` / `blink_rpm` | bool / float | rising-edge + rolling 60 s |
| `micro_events` | list[{au, peak, duration_ms}] | MAD-robust spike detector |
| `pain` | {pspi, level, confidence, trend, contributing_aus} | PSPI detector |
| `heart_rate` | {bpm, confidence, snr, quality, is_abnormal, abnormality} | rPPG estimator |
| `distress` | {comfort, arousal, pain, engagement, tag, observations, confidence} | rule-based inference |
| `alerts` | list[{key, level, reason, evidence}] | AlertEngine |
| `clinical_summary` | str | LLM (rate-limited) |
| `fps` | float | moving average |

### C. Module layout

```
src/care_monitor/
├── config.py         pydantic-settings, env-driven
├── perception/
│   ├── face_mesh.py  MediaPipe VIDEO mode (CPU delegate)
│   ├── head_pose.py  4×4 → ZYX Euler angles
│   └── iris_gaze.py  iris / eye-corner ratios → averted flag
├── features/
│   ├── action_units.py  EMA smoother + amplification
│   ├── blink.py         rising-edge + rolling 60 s rate
│   ├── micro_expressions.py  MAD-robust spike detector
│   ├── pain.py          PSPI + trend + confidence
│   └── rppg.py          forehead green bandpass + FFT + SNR gate
├── inference/
│   ├── distress_state.py  4 dimensions + behavioural tag
│   ├── alerts.py          cooldown + consecutive-frame engine
│   └── llm_reasoner.py    Groq / Ollama, constrained prompt
├── privacy.py         ConsentStore (TTL) + redaction helpers
└── agent.py           per-session orchestrator

app/
├── server.py          FastAPI + WS + Prometheus + consent gate
└── dashboard_html.py  embedded single-page dashboard

tests/test_care_monitor.py   18 tests, 0.6 s
```

### D. Deployment artefact

The Dockerfile (`Dockerfile.new`) is single-stage, `python:3.12-slim`, installs `libgl1`, `libglib2.0-0`, and `libgomp1`, and runs `uvicorn app.server:app`. Image ≈ 400 MB; boot to healthy `/health` on Render free tier ≈ 8 s; cold-frame latency measured in §V.B. No Nginx, no `/static` mount, no Jinja2 — the dashboard HTML/CSS/JS is an embedded Python string in `app/dashboard_html.py`. This single-binary design was chosen after direct experience with static-file-serving failures on Render and Railway.

---

## IV. Methods

### A. Perception

We use **MediaPipe FaceLandmarker** in `RunningMode.VIDEO` with the CPU delegate. VIDEO mode gives temporal tracking consistency at the cost of a monotonically-increasing timestamp requirement, which we satisfy by passing `int((time.time() - t0) * 1000)` per frame. Forcing the CPU delegate eliminates the OpenGL/GLES dependency that breaks deployment on stripped-down cloud containers. Configuration: `num_faces = 1`; `min_{face_detection, face_presence, tracking}_confidence = 0.5`.

Output per frame: 478 3-D landmarks (468 base mesh + 10 iris-refined), 52 ARKit-compatible blendshape coefficients ∈ [0, 1], and a 4×4 facial transformation matrix.

### B. Head pose

The 4×4 transformation matrix is decomposed by the ZYX Euler convention. Letting $R$ be the rotation sub-matrix and $s_y = \sqrt{R_{00}^2 + R_{10}^2}$:

$$
\text{pitch} = \arctan2(R_{21}, R_{22}), \quad
\text{yaw} = \arctan2(-R_{20}, s_y), \quad
\text{roll} = \arctan2(R_{10}, R_{00})
\tag{1}
$$

converted to degrees. A unit-test asserts $R = I \Rightarrow (0°, 0°, 0°)$.

### C. Action Units

We define a fixed **blendshape → AU mapping** $M$ (20 AUs, Appendix A). For a blendshape-score dictionary $b$, the raw AU vector is:

$$
a_{\text{raw}}(u) = \alpha_u \cdot \frac{1}{|M(u)|} \sum_{n \in M(u)} b(n)
\tag{2}
$$

with per-AU amplification $\alpha_u$ (Appendix A) calibrated so that mild expressions cross the $a_u > 0.15$ activation threshold of [8]. The `mouthClose` blendshape is inverted for AU25. AUs are clipped to [0, 1].

Exponential-moving-average smoothing over a sliding 5-frame window:

$$
s_u^{t} = \alpha s_u^{t-1} + (1 - \alpha) a_u^t, \quad \alpha = 0.35
\tag{3}
$$

If an AU is absent at frame $t$, it decays by $(1 - \alpha)$ instead of holding, preventing stale activations. A unit test asserts convergence under constant input and decay under absence.

### D. Temporal features

**Blink detection.** A rising edge on AU45 with a 0.15-s refractory period registers a blink event. Blink-rate-per-minute is the count of events inside a rolling 60-s window, projected linearly when the window is partially filled. Tested.

**Micro-expressions.** For each AU we maintain a 60-frame history. The activation threshold is MAD-robust:

$$
\tau_u = \mathrm{median}(h_u) + k \cdot 1.4826 \cdot \mathrm{MAD}(h_u), \quad k = 4
\tag{4}
$$

where 1.4826 is the MAD-to-σ factor for a Gaussian. A micro-event is logged when $a_u > \tau_u$ for $1 \le n_f \le 15$ consecutive frames, then drops below $\tau_u$. AU, peak intensity, and duration (ms) are recorded. Tested on an isolated-spike synthetic trace.

**PSPI pain detector.** Each [0, 1] AU is mapped to the FACS A-E [0, 5] scale by multiplication by 5, PSPI is computed by the canonical Prkachin–Solomon formula, and a weighted moving average applied:

$$
\widehat{\mathrm{PSPI}}_t = \frac{\sum_{i=t-w+1}^{t} w_i \cdot \mathrm{PSPI}_i}{\sum_{i=t-w+1}^{t} w_i}, \quad
w_i = \tfrac{1}{2} + \tfrac{i - (t-w+1)}{2(w-1)}
\tag{5}
$$

with $w = 15$. The classifier is

$$
\mathcal{L}(\widehat{\mathrm{PSPI}}) = \begin{cases}
\textsc{severe} & \widehat{\mathrm{PSPI}} \ge 8 \\
\textsc{moderate} & 4 \le \widehat{\mathrm{PSPI}} < 8 \\
\textsc{mild} & 1.5 \le \widehat{\mathrm{PSPI}} < 4 \\
\textsc{none} & \text{otherwise}
\end{cases}
\tag{6}
$$

Thresholds are env-tunable. Confidence is $\max(0, 1 - \sigma_5 / 5)$, where $\sigma_5$ is the local standard deviation over the last 5 frames. Trend (`increasing` / `decreasing` / `stable` / `insufficient_data`) is a 3-vs-3 recent-vs-older mean comparison with a 0.5 threshold.

### E. rPPG heart rate

The forehead ROI is defined by MediaPipe landmark indices $\{10, 67, 69, 104, 108, 151, 337, 299, 297, 333\}$ — a stable region between brows and hairline. Each frame pushes the spatial mean of the green channel onto a rolling 300-frame buffer $g$. When $|g| \ge 5 f_s$ (default $f_s = 30$ Hz), we detrend, z-normalise, apply a Butterworth 3rd-order bandpass $[0.7, 4.0]$ Hz (= [42, 240] BPM), FFT, and take the dominant frequency:

$$
\mathrm{BPM} = 60 \cdot \arg\max_{f \in [0.7, 4.0]} \bigl|\mathcal{F}\{\mathrm{BP}(z(\mathrm{detrend}(g)))\}\bigr|(f)
\tag{7}
$$

**Signal-to-noise gate.**

$$
\mathrm{SNR} = \frac{P_{\text{peak}}}{\sum P - P_{\text{peak}} + 10^{-10}}
\tag{8}
$$

Output is bucketed as *good* (SNR > 0.3), *fair* (0.15–0.3), *poor* (< 0.15), or *no_signal*. **We refuse to emit a BPM in the *poor* bucket** — a deliberate false-positive-suppression choice motivated by the demographic-bias evidence in [31], [32].

### F. Dimensional distress inference

Let $a$ be the smoothed AU vector, $p$ the head pose (deg), $g$ the gaze state, $b$ the blink rate per minute, $\Pi$ the PSPIAssessment, $\beta$ the rPPG BPM (possibly 0), and $q$ the rPPG quality band. Four dimensions in [0, 1] are produced by transparent, auditable rules (code: `src/care_monitor/inference/distress_state.py`):

$$
\text{pain} = \min\!\left(1, \frac{\widehat{\mathrm{PSPI}}}{16}\right)
\tag{9}
$$

$$
\begin{aligned}
\text{comfort} &= \mathrm{clip}_{[0,1]}\Bigl(1 - \text{pain} \\
&\quad - 0.1\,\mathbb{1}[a_{AU4}] - 0.1\,\mathbb{1}[a_{AU15}] - 0.1\,\mathbb{1}[a_{AU20}] \\
&\quad + 0.1\,\mathbb{1}[a_{AU6} \wedge a_{AU12}]\Bigr)
\end{aligned}
\tag{10}
$$

where $\mathbb{1}[a_u] = 1$ iff $a_u > 0.15$ and the last term captures the Duchenne-smile pattern.

$$
\begin{aligned}
\text{arousal} &= \mathrm{clip}_{[0,1]}\Bigl(0.5 \\
&\quad + 0.2\,\mathbb{1}[b > 25] - 0.15\,\mathbb{1}[0 < b < 8] \\
&\quad + 0.15\,\mathbb{1}[\beta > 100 \wedge q \ne \text{poor}] \\
&\quad - 0.1\,\mathbb{1}[0 < \beta < 60 \wedge q \ne \text{poor}] \\
&\quad + 0.1\,\mathbb{1}[\textstyle\sum_u a_u > 2] + 0.3 \cdot \text{pain}\Bigr)
\end{aligned}
\tag{11}
$$

$$
\begin{aligned}
\text{engagement} &= \mathrm{clip}_{[0,1]}\Bigl(0.5 \\
&\quad + 0.15\,\mathbb{1}[|p_{\text{yaw}}| < 20 \wedge |p_{\text{pitch}}| < 15] \\
&\quad + 0.2\,\mathbb{1}[\neg g_{\text{averted}}] - 0.3\,\mathbb{1}[a_{AU43} > 0.5]\Bigr)
\end{aligned}
\tag{12}
$$

A **behavioural tag** is drawn from the fixed list in Table III via a most-specific-first rule ladder. Tag confidence is prior-in-the-rule, not learned.

**Table III. Fixed behavioural-tag vocabulary. None names an emotion.**

| Tag | Triggering evidence pattern |
|-----|----------------------------|
| `grimace_pattern_severe` | PSPI level = severe |
| `grimace_pattern_moderate` | PSPI level = moderate |
| `furrowed_concentrating_or_confused` | AU4 ∧ AU7 ∧ \|roll\| > 10° |
| `high_cognitive_load_or_fatigue` | AU4 ∧ 0 < blink < 10/min |
| `agitation_pattern` | blink > 25/min ∧ AU4 |
| `withdrawn_or_disengaged` | Σa < 1.0 ∧ blink < 8 ∧ gaze averted |
| `duchenne_smile_pattern` | AU6 ∧ AU12 |
| `social_smile_pattern` | AU12 ∧ ¬AU6 |
| `engaged_expressive` | stable head ∧ not averted ∧ Σa > 0.3 |
| `gaze_averted` | gaze averted |
| `neutral` | default |

### G. Alert engine

The alert engine (`src/care_monitor/inference/alerts.py`) fires key $k$ at time $t$ iff

$$
\mathbb{1}[\mathrm{cond}_k(t)] \wedge \bigl(\mathrm{streak}_k \ge N\bigr) \wedge \bigl(t - t_{\mathrm{last}, k} \ge T_{\mathrm{cool}}\bigr)
\tag{13}
$$

with $N = 5$ frames and $T_{\mathrm{cool}} = 30$ s by default. When the condition becomes false, $\mathrm{streak}_k \gets 0$. On fire, $t_{\mathrm{last}, k} \gets t$, $\mathrm{streak}_k \gets 0$, and the alert is emitted with a human-readable `reason` and a structured `evidence` dict (e.g. `{pspi: 9.1, confidence: 0.82, AU4: 0.9, AU43: 0.8}`).

Five keys are defined:

| key | level | condition |
|-----|-------|-----------|
| `severe_pain` | **urgent** | PSPI level = severe |
| `moderate_pain` | concern | PSPI level = moderate |
| `tachycardia` | concern | rPPG > 100 BPM, quality ≠ poor, conf > 0.4 |
| `bradycardia` | concern | rPPG < 60 BPM, quality ≠ poor, conf > 0.4 |
| `low_comfort` | attention | comfort < 0.25, confidence > 0.5 |

Unit tests assert both the consecutive-frame and the cooldown gates.

### H. Grounded LLM reasoner

We build a **snapshot** dict $\sigma$ containing: active AUs (rounded to 2 dp), head pose (rounded to 1°), gaze, blink rpm, PSPI and level, rPPG BPM and quality band, behavioural tag, observation list, and the three most recent micro-events. The LLM never sees a raw frame.

The system prompt enforces six hard rules:

1. Output MUST start with the literal string `STATE:`.
2. Output MUST use hedging words: *possibly*, *appears*, *may*, *consistent with*.
3. Output MUST cite at least one AU (or rPPG, or PSPI).
4. Output MUST NOT be a diagnosis; claiming to "detect emotion" is banned.
5. If PSPI ≥ 4 OR pain level = severe, output MUST recommend caregiver check-in.
6. If no salient signals, output MUST be exactly `STATE: No salient distress signals observed.`

The full prompt is reproduced in Appendix B. Any response missing the `STATE:` prefix is auto-patched on ingress. The reasoner is rate-limited to one call per 3 seconds; we measured zero rate-quota violations against Groq's free-tier Llama-3.3-70B over a continuous 1 h session. Ollama (local e.g. `llama-3.2-3b`) is a drop-in alternative for offline deployment; `LLM_PROVIDER=none` disables the layer entirely with every other pipeline stage unaffected.

### I. Privacy gate

`src/care_monitor/privacy.py` + `app/server.py`:

- A `ConsentStore` holds per-session `ConsentRecord` objects (`session_id`, `granted_at`, `ttl_seconds`, `purpose`, IP hash).
- `POST /api/consent` grants; `POST /api/consent/revoke` removes the session and consent.
- The `/ws` handler calls `CONSENT.is_valid(session_id)` before accepting any frame, closing the WebSocket with code 4403 otherwise.
- **No raw frame is written to disk** (`STORE_RAW_FRAMES=false` default). When enabled, `redact_frame_for_log()` Gaussian-blurs the eye and mouth ROIs before persistence.
- A background coroutine prunes expired sessions and consents every 60 s.
- `POST /api/data/export` (GDPR Art. 15) returns a numeric-only session summary.
- `POST /api/data/delete` (GDPR Art. 17) removes the session from memory and invalidates the consent.

---

## V. Software Evaluation

This paper reports **software** measurements. Clinical validation is future work (§VI).

### A. Unit-test suite

Eighteen pure-Python unit tests cover every inference rule (Table IV). All pass in 0.6 s on a commodity CPU (Python 3.12, x86_64, no AVX-512).

**Table IV. Unit-test coverage.**

| # | Property tested |
|---|-----------------|
| 1 | Blendshape → AU bilateral-average correctness |
| 2 | AU25 inversion from `mouthClose` |
| 3 | Active-AU threshold semantics (strict >) |
| 4 | EMA smoother converges to steady state |
| 5 | EMA smoother decays absent AUs |
| 6 | Blink rising-edge fires once per closure |
| 7 | Blink rate scales correctly to per-minute |
| 8 | Micro-expression spike detector on synthetic trace |
| 9 | PSPI formula matches Prkachin–Solomon to 1e-6 |
| 10 | PSPI severity classifier thresholds (Eq. 6) |
| 11 | PSPI trend detection on increasing series |
| 12 | Distress tag = `grimace_pattern_severe` on full-PSPI pattern |
| 13 | Distress tag = `duchenne_smile_pattern` on AU6+AU12 |
| 14 | Distress tag on quiet, averted face |
| 15 | Alerts require N consecutive frames (Eq. 13) |
| 16 | Alerts respect cooldown window |
| 17 | Head pose from identity matrix → (0°, 0°, 0°) |
| 18 | `head_stable` predicate negative on extremes |

### B. Runtime performance

Measured on a free-tier Render container (0.5 vCPU, 512 MB RAM, Python 3.12, no AVX-512):

| Metric | Value |
|--------|------:|
| Cold boot → `/health` OK | ≈ 8 s |
| First-frame latency (model cold) | ≈ 150 ms |
| Steady-state per-frame latency | ≈ 90 ms |
| Sustainable client FPS (one session) | 8-10 |
| Memory after model load | ≈ 350 MB |
| Docker image size | ≈ 400 MB |
| Prometheus metrics exposed | `care_mm_{frames, alerts, active_sessions, frame_latency_seconds}` |

The 90-ms latency comfortably meets the 125-ms budget of the 8-FPS client stream.

### C. What this evaluation is **not**

It is not:
- a precision/recall number on UNBC-McMaster or BioVid — we have not run those benchmarks because we will not conflate *software* contributions with *clinical* claims; §VI defines that study;
- a PAINAD-concordance number — future work;
- a fairness number across Fitzpatrick I-VI — future work.

We explicitly refuse to quote a benchmark accuracy until we have run the studies in §VI.

---

## VI. Proposed Clinical Validation Protocol

This section specifies the studies that must precede any patient-facing use.

### A. Study 1 — PSPI benchmark on UNBC-McMaster

**Data.** UNBC-McMaster Shoulder Pain Archive [3]: 200 videos, 48,398 FACS-coded frames, 129 participants.

**Metrics.** (i) Frame-level Pearson correlation of $\widehat{\mathrm{PSPI}}$ vs. ground truth. (ii) Binary precision/recall/F1 at threshold PSPI ≥ 4 (= moderate). (iii) Frame-level MAE.

**Baselines.** Classical (Saxen & Al-Hamadi 2015, ~87 % frame-level accuracy) [38]; deep (Werner *et al.* 2017 [20]); ConvNeXt+LSTM (Cen *et al.* 2025 [4]); transformer multimodal (Gkikas *et al.* 2024 [5]).

**Expected outcome.** CARE-MM's blendshape-derived PSPI will likely under-perform end-to-end trained baselines on correlation but should remain competitive on binary pain detection (the clinically actionable signal). If confirmed, this trades marginal benchmark accuracy for full auditability.

### B. Study 2 — PAINAD concordance on a dementia cohort

**Design.** Prospective, non-interventional, IRB-approved, single-site. $n \ge 30$ residents with advanced dementia (MMSE < 12).

**Protocol.** Two trained nurses independently PAINAD-score each patient at 10 random 5-min observation windows across a 24 h window, while CARE-MM runs continuously. Each nurse PAINAD score is paired with the CARE-MM 5-min window containing it.

**Metrics.**
- Cohen's κ inter-rater agreement between the two nurses.
- Cohen's κ between median nurse PAINAD and the CARE-MM alert (binarised as *any severe_pain or moderate_pain alert*) in that window.
- ROC of $\max_{t \in \text{window}} \widehat{\mathrm{PSPI}}$ against median nurse PAINAD.
- Per-patient observation-hours captured by CARE-MM vs. nurse observation-minutes.

**Success criterion.** κ between CARE-MM alert and median nurse PAINAD > 0.4 (moderate agreement), with CARE-MM providing strictly more temporal coverage per patient per shift.

### C. Study 3 — Fairness audit across Fitzpatrick I-VI

Motivated by [31], [32]. Recruit a balanced cohort across Fitzpatrick skin-tone bins I-II, III-IV, V-VI, target $n \ge 10$ per bin. Primary outcome: rPPG BPM MAE against contact-PPG ground truth (Polar H10 chest strap). Expected: the SNR gate will bucket a higher fraction of V-VI frames as *poor* and refuse output, rather than silently mis-reporting — the failure mode [32] identifies in deep rPPG.

### D. Study 4 — Alert-fatigue measurement

Protocol: a 40-shift (~320 h) deployment in a single long-term-care unit. Measure alarms/hour, alarm/patient/shift, false-positive rate (nurse-adjudicated), and the Charité Alarm-Fatigue Scale on participating nurses [35]. Target: median alarms/patient/shift < 3 (vs. the hundreds reported in ICU settings [34], [37]).

### E. Study 5 — LLM hallucination audit

Protocol: 500 real-session `snapshot → STATE:` pairs reviewed by two FACS-certified clinicians using the CREOLA framework [17]. Metrics: hallucination rate, omission rate, compliance with each of the six hard prompt rules (§IV.H). Target: hallucination rate ≤ 1.5 % (matching [17]); prompt-rule compliance ≥ 99 %.

---

## VII. Discussion, Limitations, and Ethics

### A. Why rules + grounded LLM, not end-to-end learning

An end-to-end CNN could score higher on UNBC-McMaster. We deliberately chose the transparent, rule-based pipeline for three reasons:

1. **Auditability.** Every score traces to specific AUs. No clinical alarm should be a black box. Benavent-Lledo *et al.* (2023) [16] explicitly call for approaches "aligned with clinical interpretability."
2. **Dataset-shift robustness.** Rule thresholds are drawn from the peer-reviewed PSPI literature, not from a training set — so there is no model to retrain on each new hospital's demographics. Barrett [2] warns that configuration-to-state maps are culture-variable; a rule that cites the muscle is robust to that variability in a way a learned end-to-end classifier is not.
3. **Barrett-consistency.** Rule-based *pattern tags* make it easier to stay disciplined about not claiming to detect emotions.

The LLM layer is **grounded** — never pixels, only rule outputs — and **constrained** to produce hedged, evidence-citing text. This is the strategy that pushed [8] to 93.3 % on CASME II and that [17] validated as pushing clinical hallucination below human baselines.

### B. Known biases

- **Skin-tone bias in rPPG.** Documented by [31], [32]; chrominance-based rPPG drops from MAE 5.2 bpm on Fitzpatrick I-III to 14.1 bpm on V-VI (p < 0.01). Our SNR gate refuses to emit a BPM in *poor* quality but does not structurally solve the bias. §VI.C is the necessary audit.
- **Blendshape → AU mapping calibration.** MediaPipe training data is predominantly Euro-facial. Benchmarks on non-Euro datasets are future work.
- **Mask / ventilator / spectacle confounders.** Mid-face occlusion degrades AU estimates and would mask the PSPI signal.
- **Pain-stoicism bias.** Patients who culturally suppress pain display will be under-flagged — the same bias that affects human observers using PAINAD or CPOT.
- **LLM demographic bias.** Groq Llama-3.3-70B was trained on Common-Crawl-scale text; its hedging vocabulary is English-weighted. Non-English prompts are not currently supported.

### C. Threat model

We assume an honest caregiver operating on a reasonably-trusted device. We do not defend against a malicious caregiver, a compromised browser, or a state-level adversary. Any real deployment MUST:
- conduct a GDPR Art. 9 Data Protection Impact Assessment;
- front the service with HTTPS (Render provides this automatically);
- store the Groq API key in the platform secret manager, never in the image;
- tie consent to a real identity flow (OAuth / SSO), not the demo flow in this repo.

### D. Ethics

CARE-MM outputs **must not** be used for:
- hiring, insurance, legal, disciplinary, or policing decisions;
- continuous-restraint justification in any care setting;
- automated triage without clinician review.

The Joint Commission principle "alarms must be actionable" [10] is the governing constraint on alert design; the reason/evidence pair on every alert is the concrete implementation.

### E. Barrett-compliance as a design constraint, not a slogan

C1 is not cosmetic. The word *emotion* appears in the `src/care_monitor/` source **only in docstrings explicitly describing what we refuse to do** (e.g., `distress_state.py`: "no discrete 'emotion labels'") and in the LLM system prompt's negation rule ("DO NOT claim to 'detect emotions'"). It is **never** a value of any field in `FrameAnalysis`, and the `behavioural_tag` enum is grep-verifiable as drawn from the fixed Table III vocabulary. A simple CI check (`! grep -q "emotion" <(jq -c '.distress.tag' session.jsonl)`) enforces this invariant on logged output.

---

## VIII. Future Work

- Execute the five studies in §VI and publish results.
- **Voice prosody** fusion (jitter, shimmer, pitch variability).
- **Personalised baselines** per patient — adapt the EMA neutral level over the first 5 min.
- **Edge deployment** via MediaPipe WASM so no frame leaves the bedside device.
- **FHIR emission** of observations (`Observation.code = LOINC 72514-3 "Pain severity"`) into a standard EHR.
- **Multi-face support** for shared rooms (currently forced to `num_faces = 1`).
- **Monk-skin-tone-scale** logging per session for on-device fairness metrics.
- **Formal differential-privacy accounting** on persisted aggregate metrics.

---

## IX. Conclusion

We have presented **CARE-MM**, a research-software artefact synthesising three decades of FACS / PSPI clinical pedigree, a modern grounded-LLM reasoning layer, an alert-fatigue-aware gating engine, and a consent-first privacy architecture into a single-binary, CPU-only, browser-deployable monitor for non-verbal clinical populations. We refuse to quote a benchmark number until the clinical protocol in §VI has been run. We **do** quote 18 passing unit tests in 0.6 s, a 90 ms per-frame latency on free-tier infrastructure, zero emotion-label outputs (Barrett-compliance), and a fully auditable pipeline in which every alert carries its evidence. The contribution is a **clinically-shaped deployment artefact**, offered as a foundation on which others can run the validation studies that this architecture is explicitly engineered to support.

---

## References

*IEEE style, numbered by first citation.*

1.  K. Herr, P. J. Coyne, T. Key, R. Manworren, M. McCaffery, S. Merkel, J. Pelosi-Kelly, and L. Wild, "Pain assessment in the nonverbal patient: Position statement with clinical practice recommendations," *Pain Management Nursing*, vol. 7, no. 2, pp. 44–52, 2006.

2.  L. F. Barrett, R. Adolphs, S. Marsella, A. M. Martinez, and S. D. Pollak, "Emotional expressions reconsidered: Challenges to inferring emotion from human facial movements," *Psychological Science in the Public Interest*, vol. 20, no. 1, pp. 1–68, 2019.

3.  P. Lucey, J. F. Cohn, K. M. Prkachin, P. E. Solomon, and I. Matthews, "Painful data: The UNBC-McMaster shoulder pain expression archive database," in *Proc. IEEE Int. Conf. Automatic Face Gesture Recognition (FG)*, 2011, pp. 57–64.

4.  Authors of arXiv:2501.06787, "Improving pain classification using spatio-temporal deep learning approaches with facial expressions," *arXiv preprint arXiv:2501.06787*, 2025.

5.  S. Gkikas, N. S. Tachos, S. Andreadis, V. C. Pezoulas, D. Zaridis, G. Gkois, A. Matonaki, T. G. Stavropoulos, and D. I. Fotiadis, "Multimodal automatic assessment of acute pain through facial videos and heart rate signals utilizing transformer-based architectures," *Frontiers in Pain Research*, vol. 5, 1372814, 2024.

6.  K. M. Prkachin and P. E. Solomon, "The structure, reliability, and validity of pain expression: Evidence from patients with shoulder pain," *Pain*, vol. 139, no. 2, pp. 267–274, 2008.

7.  M. Z. Poh, D. J. McDuff, and R. W. Picard, "Non-contact, automated cardiac pulse measurements using video imaging and blind source separation," *Optics Express*, vol. 18, no. 10, pp. 10762–10774, 2010.

8.  G. L. Sălăgean, M. Leba, and A. C. Ionică, "Seeing the unseen: Real-time micro-expression recognition with action units and GPT-based reasoning," *Applied Sciences*, vol. 15, no. 12, 6417, 2025.

9.  S. Sendelbach and M. Funk, "Alarm fatigue: A patient safety concern," *AACN Advanced Critical Care*, vol. 24, no. 4, pp. 378–386, 2013.

10. The Joint Commission, "Sentinel Event Alert #50: Medical device alarm safety in hospitals," 2013.

11. V. Warden, A. C. Hurley, and L. Volicer, "Development and psychometric evaluation of the Pain Assessment in Advanced Dementia (PAINAD) scale," *J. American Medical Directors Assoc.*, vol. 4, no. 1, pp. 9–15, 2003.

12. L. M. Breau *et al.*, "Psychometric properties of the non-communicating children's pain checklist — revised," *Pain*, vol. 99, no. 1-2, pp. 349–357, 2002.

13. C. Gélinas, L. Fillion, K. A. Puntillo, C. Viens, and M. Fortier, "Validation of the Critical-Care Pain Observation Tool (CPOT) in adult patients," *American J. Critical Care*, vol. 15, no. 4, pp. 420–427, 2006.

14. L. Achterberg *et al.*, "Pain management in patients with dementia," *Clinical Interventions in Aging*, vol. 8, pp. 1471–1482, 2013.

15. P. Ekman and W. V. Friesen, *Facial Action Coding System: A Technique for the Measurement of Facial Movement*. Palo Alto, CA: Consulting Psychologists Press, 1978.

16. M. Benavent-Lledo, D. Mulero-Pérez, D. Ortiz-Perez, J. Rodriguez-Juan, A. Berenguer-Agullo, A. Psarrou, and J. Garcia-Rodriguez, "A comprehensive study on pain assessment from multimodal sensor data," *Sensors*, vol. 23, no. 24, 9675, 2023.

17. E. Asgari, N. Montaña-Brown, M. Dubois, S. Khalil, J. Balloch, J. Au Yeung, and D. Pimenta, "A framework to assess clinical safety and hallucination rates of LLMs for medical text summarisation," *npj Digital Medicine*, vol. 8, 274, 2025.

18. K. M. Prkachin, "The consistency of facial expressions of pain: A comparison across modalities," *Pain*, vol. 51, no. 3, pp. 297–306, 1992.

19. P. Werner, A. Al-Hamadi, R. Niese, S. Walter, S. Gruss, and H. C. Traue, "Towards pain monitoring: Facial expression, head pose, a new database, an automatic system and remaining challenges," in *Proc. BMVC*, 2013.

20. P. Werner, A. Al-Hamadi, K. Limbrecht-Ecklundt, S. Walter, S. Gruss, and H. C. Traue, "Automatic pain assessment with facial activity descriptors," *IEEE Trans. Affective Computing*, vol. 8, no. 3, pp. 286–299, 2017.

21. D. Zaripova *et al.*, "A review of automatic pain assessment from facial information using machine learning," *Technologies*, vol. 12, no. 6, 92, 2024.

22. T. Baltrušaitis, A. Zadeh, Y. C. Lim, and L.-P. Morency, "OpenFace 2.0: Facial behavior analysis toolkit," in *Proc. IEEE FG*, 2018, pp. 59–66.

23. J. H. Cheong *et al.*, "Py-Feat: Python facial expression analysis toolbox," *Affective Science*, vol. 4, pp. 781–796, 2023.

24. Google LLC, "MediaPipe FaceLandmarker documentation," 2024. [Online]. Available: https://ai.google.dev/edge/mediapipe/solutions/vision/face_landmarker

25. Py-Feat Team, "MP-Blendshapes model card," Hugging Face, 2024. [Online]. Available: https://huggingface.co/py-feat/mp_blendshapes

26. A. Lichtner *et al.*, "Multi-center validation of the Pain Assessment in Advanced Dementia scale," *Behavioral Sciences*, vol. 5, no. 3, 52, 2023.

27. W. Verkruysse, L. O. Svaasand, and J. S. Nelson, "Remote plethysmographic imaging using ambient light," *Optics Express*, vol. 16, no. 26, pp. 21434–21445, 2008.

28. G. de Haan and V. Jeanne, "Robust pulse rate from chrominance-based rPPG," *IEEE Trans. Biomedical Engineering*, vol. 60, no. 10, pp. 2878–2886, 2013.

29. W. Wang, A. C. den Brinker, S. Stuijk, and G. de Haan, "Algorithmic principles of remote PPG," *IEEE Trans. Biomedical Engineering*, vol. 64, no. 7, pp. 1479–1491, 2016.

30. W. Chen and D. McDuff, "DeepPhys: Video-based physiological measurement using convolutional attention networks," in *Proc. ECCV*, 2018, pp. 349–365.

31. E. M. Nowara, D. McDuff, and A. Veeraraghavan, "A meta-analysis of the impact of skin tone and gender on non-contact photoplethysmography measurements," in *Proc. IEEE FG*, 2020.

32. M. Bondarenko, C. Menon, and M. Elgendi, "Demographic bias in public remote photoplethysmography datasets," *npj Digital Medicine*, vol. 8, 561, 2025.

33. W.-J. Yan, X. Li, S.-J. Wang, G. Zhao, Y.-J. Liu, Y.-H. Chen, and X. Fu, "CASME II: An improved spontaneous micro-expression database and the baseline evaluation," *PLOS ONE*, vol. 9, no. 1, e86041, 2014.

34. Nurse.org Editorial, "Alarm fatigue statistics: 350 alarms per patient per day in ICU," 2024. [Online]. Available: https://nurse.org/articles/alarm-fatigue-statistics-patient-safety/

35. T. Geiger *et al.*, "Assessment of alarm fatigue among intensive care unit nurses: A cross-sectional study," *BMC Nursing*, vol. 24, 2025.

36. Y. Nyarko, Z. Yin, X. Chai *et al.*, "Nurses' alarm fatigue, influencing factors, and its relationship with burnout in the critical care units: A cross-sectional study," *Australian Critical Care*, vol. 37, no. 2, pp. 273–280, 2024.

37. Editorial, "Improving alarm management to reduce alarm fatigue in critical care: A systematic review," *Intensive and Critical Care Nursing*, 2025.

38. F. Saxen and A. Al-Hamadi, "Learning appearance features for pain detection using the UNBC-McMaster shoulder pain expression archive database," in *Proc. Int. Conf. Computer Vision Systems*, 2015.

39. A. Mehrabian, "Pleasure-Arousal-Dominance: A general framework for describing and measuring individual differences in temperament," *Current Psychology*, vol. 14, no. 4, pp. 261–292, 1996.

40. J. A. Russell, "A circumplex model of affect," *J. Personality and Social Psychology*, vol. 39, no. 6, pp. 1161–1178, 1980.

41. T. Soukupová and J. Čech, "Real-time eye blink detection using facial landmarks," in *21st Computer Vision Winter Workshop*, 2016.

42. Joint Commission, "National Patient Safety Goal on clinical alarm safety (NPSG.06.01.01)," 2014.

43. European Union, "General Data Protection Regulation (GDPR), Article 9: Processing of special categories of personal data," *Official Journal of the European Union*, L 119/1, 2016.

---

## Appendix A — Blendshape ↔ Action Unit mapping

**Table A.I. Full AU ↔ MediaPipe blendshape table with per-AU amplification $\alpha_u$.**

| AU | FACS description | MediaPipe blendshape(s) | $\alpha_u$ |
|----|------------------|-------------------------|:----------:|
| 1  | Inner brow raise | browInnerUp | 2.0 |
| 2  | Outer brow raise | browOuterUpLeft / Right | 1.8 |
| 4  | Brow lowerer | browDownLeft / Right | 2.0 |
| 5  | Upper-lid raise | eyeWideLeft / Right | 2.0 |
| 6  | Cheek raise (Duchenne) | cheekSquintLeft / Right | 2.0 |
| 7  | Lid tightener | eyeSquintLeft / Right | 3.0 |
| 9  | Nose wrinkler | noseSneerLeft / Right | 3.0 |
| 10 | Upper-lip raiser | mouthUpperUpLeft / Right | 2.5 |
| 12 | Lip-corner puller (smile) | mouthSmileLeft / Right | 3.0 |
| 14 | Dimpler | mouthDimpleLeft / Right | 2.2 |
| 15 | Lip-corner depressor | mouthFrownLeft / Right | 3.0 |
| 17 | Chin raiser | mouthShrugLower | 2.0 |
| 20 | Lip stretcher | mouthStretchLeft / Right | 3.0 |
| 23 | Lip tightener | mouthPressLeft / Right | 2.0 |
| 24 | Lip pucker | mouthPucker | 2.0 |
| 25 | Lips part | $1 - $ mouthClose | 1.0 |
| 26 | Jaw drop | jawOpen | 2.5 |
| 28 | Lip roll | mouthRollLower / Upper | 1.5 |
| 43 | Eyes closed | eyeLookDownLeft / Right (+ AU45 proxy) | 1.5 |
| 45 | Blink | eyeBlinkLeft / Right | 1.0 |

---

## Appendix B — LLM System Prompt (verbatim)

```
You are a clinical affective-computing assistant advising a caregiver who is
remotely monitoring a non-verbal or communication-impaired patient (e.g.,
dementia, ICU-intubated, pediatric, post-stroke aphasia).

You are given:
  - FACS Action Unit intensities (from MediaPipe blendshapes)
  - Head pose / gaze / blink rate
  - PSPI pain score (Prkachin & Solomon 1992; 0-16 scale)
  - Heart rate (from rPPG; may be noisy)
  - Rule-based behavioural tag and short observation list

TASK: produce ONE short hedged clinical-observation sentence (< 25 words)
that a caregiver can act on. Follow ALL of these rules:
  1. Start with "STATE:" exactly.
  2. Use hedging words: "possibly", "may", "appears", "consistent with".
  3. Cite at least one AU (e.g., "AU4", "AU6+AU12") or rPPG or PSPI.
  4. DO NOT output a diagnosis. DO NOT claim to "detect emotions".
  5. If PSPI >= 4 or severe pain level, recommend caregiver check-in.
  6. If no salient signals, say exactly: "STATE: No salient distress signals observed."
```

Changes to this prompt should be versioned and justified in the commit log, because prompt engineering in a clinical setting is itself a regulated-device concern.

---

## Appendix C — Reproducibility

```bash
git clone https://github.com/Mahesh2023/patient-care-monitor.git
cd patient-care-monitor
git checkout feature/care-mm-rewrite

cp .env.example .env
# optional: paste a free Groq API key from https://console.groq.com/keys
#   GROQ_API_KEY=gsk_...

pip install -r requirements-new.txt
PYTHONPATH=. pytest tests/test_care_monitor.py -v   # 18 tests, ≈ 0.6 s
PYTHONPATH=. uvicorn app.server:app --host 0.0.0.0 --port 8000
# open http://localhost:8000
```

Docker:

```bash
docker build -f Dockerfile.new -t care-mm:2.0 .
docker run -e GROQ_API_KEY=$GROQ_API_KEY -p 8000:8000 care-mm:2.0
```

Render / Railway / Fly.io: use `render.yaml.new` or the equivalent Docker-based blueprint.

*End of manuscript.*
