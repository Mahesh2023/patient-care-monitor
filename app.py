"""
Patient Care Monitor - Gradio Dashboard
========================================
Real-time facial analysis with webcam streaming, pain detection,
and comprehensive research reference.

Deploy: Hugging Face Spaces (Gradio SDK)
"""

import os
import sys
import time

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import cv2
import numpy as np
import gradio as gr

from modules.face_analyzer import FaceAnalyzer, FaceAnalysisResult
from modules.pain_detector import PainDetector, PainLevel
from modules.fusion_engine import FusionEngine, PatientAlertLevel
from modules.text_sentiment import TextSentimentAnalyzer

# ─── Global State ────────────────────────────────────────────
face_analyzer = None
pain_detector = PainDetector()
fusion_engine = FusionEngine()
text_analyzer = TextSentimentAnalyzer()


def get_face_analyzer():
    """Lazy-init face analyzer (loads model once)."""
    global face_analyzer
    if face_analyzer is None:
        face_analyzer = FaceAnalyzer()
    return face_analyzer


def draw_overlay(img, face_result, pain_result, fused):
    """Draw monitoring HUD on the video frame."""
    h, w = img.shape[:2]
    overlay = img.copy()

    # Semi-transparent top bar
    cv2.rectangle(overlay, (0, 0), (w, 44), (20, 20, 30), -1)
    cv2.addWeighted(overlay, 0.75, img, 0.25, 0, img)

    # Face detection status
    if face_result.face_detected:
        cv2.putText(img, "FACE DETECTED", (12, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.65, (80, 255, 80), 2)
    else:
        cv2.putText(img, "NO FACE DETECTED", (12, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.65, (80, 80, 255), 2)
        return img

    # Pain indicator (right side of top bar)
    pain_color = (80, 255, 80)
    if pain_result.pain_level == PainLevel.MILD:
        pain_color = (80, 255, 255)
    elif pain_result.pain_level == PainLevel.MODERATE:
        pain_color = (80, 165, 255)
    elif pain_result.pain_level == PainLevel.SEVERE:
        pain_color = (80, 80, 255)

    pain_text = f"Pain: {pain_result.pspi_score:.1f} ({pain_result.pain_level.value})"
    cv2.putText(img, pain_text, (w - 320, 30),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, pain_color, 2)

    # Bottom bar -- comfort + arousal
    bar_overlay = img.copy()
    cv2.rectangle(bar_overlay, (0, h - 50), (w, h), (20, 20, 30), -1)
    cv2.addWeighted(bar_overlay, 0.75, img, 0.25, 0, img)

    # Comfort bar
    comfort_pct = fused.comfort_level
    bar_w = int((w // 2 - 30) * comfort_pct)
    cv2.rectangle(img, (12, h - 38), (w // 2 - 18, h - 18), (60, 60, 70), -1)
    bar_color = (80, 200, 80) if comfort_pct > 0.5 else (80, 165, 255)
    cv2.rectangle(img, (12, h - 38), (12 + bar_w, h - 18), bar_color, -1)
    cv2.putText(img, f"Comfort: {int(comfort_pct * 100)}%", (14, h - 42),
                cv2.FONT_HERSHEY_SIMPLEX, 0.45, (200, 200, 220), 1)

    # Arousal bar
    arousal_pct = fused.arousal_level
    a_bar_w = int((w // 2 - 30) * arousal_pct)
    x_start = w // 2 + 6
    cv2.rectangle(img, (x_start, h - 38), (w - 12, h - 18), (60, 60, 70), -1)
    a_color = (80, 80, 255) if arousal_pct > 0.6 else (200, 200, 80)
    cv2.rectangle(img, (x_start, h - 38), (x_start + a_bar_w, h - 18), a_color, -1)
    cv2.putText(img, f"Arousal: {int(arousal_pct * 100)}%", (x_start + 2, h - 42),
                cv2.FONT_HERSHEY_SIMPLEX, 0.45, (200, 200, 220), 1)

    # Alert badge
    if fused.alert_level != PatientAlertLevel.NORMAL:
        alert_colors = {
            PatientAlertLevel.ATTENTION: (80, 255, 255),
            PatientAlertLevel.CONCERN: (80, 165, 255),
            PatientAlertLevel.URGENT: (80, 80, 255),
        }
        ac = alert_colors.get(fused.alert_level, (200, 200, 200))
        label = f"ALERT: {fused.alert_level.value.upper()}"
        cv2.putText(img, label, (w // 2 - 80, 68),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.65, ac, 2)

    # Face mesh landmarks (every 3rd for performance)
    if face_result.landmarks is not None:
        for i in range(0, len(face_result.landmarks), 3):
            pt = face_result.landmarks[i]
            cv2.circle(img, (int(pt[0]), int(pt[1])), 1, (255, 220, 100), -1)

    return img


def process_frame(frame):
    """Process a single webcam frame through the full pipeline."""
    if frame is None:
        return None, "", "", "", "", "", ""

    t = time.time()
    analyzer = get_face_analyzer()

    # Run analysis pipeline
    face_result = analyzer.analyze(frame, timestamp=t)
    pain_result = pain_detector.assess(
        face_result.aus if face_result.face_detected else None, timestamp=t
    )
    fused = fusion_engine.fuse(
        face_result=face_result,
        pain_assessment=pain_result,
        timestamp=t,
    )

    # Draw overlay
    annotated = draw_overlay(frame.copy(), face_result, pain_result, fused)

    # Build metrics text
    comfort_text = f"{int(fused.comfort_level * 100)}%"
    pain_text = f"{pain_result.pspi_score:.1f} ({pain_result.pain_level.value})"
    arousal_text = f"{int(fused.arousal_level * 100)}%"
    engagement_text = f"{int(fused.engagement_level * 100)}%"
    face_text = "Detected" if face_result.face_detected else "Not detected"

    # Build observations + AU details
    details_parts = []
    if fused.observations:
        details_parts.append("**Observations:**\n" + "\n".join(f"- {o}" for o in fused.observations))
    if fused.alert_reasons:
        details_parts.append("**Alerts:**\n" + "\n".join(f"- {r}" for r in fused.alert_reasons))
    if face_result.aus:
        au_dict = face_result.aus.to_dict()
        active = {k: v for k, v in au_dict.items() if v > 0.1}
        if active:
            au_lines = [f"- {k}: {v:.2f}" for k, v in sorted(active.items(), key=lambda x: -x[1])]
            details_parts.append("**Active Action Units:**\n" + "\n".join(au_lines))
    details = "\n\n".join(details_parts) if details_parts else "Monitoring..."

    return annotated, comfort_text, pain_text, arousal_text, engagement_text, face_text, details


def analyze_text(text):
    """Analyze caregiver notes for sentiment and pain/distress indicators."""
    if not text or not text.strip():
        return "", "", "", "", ""
    result = text_analyzer.analyze(text, time.time())
    valence = f"{int(result.valence * 100)}%"
    arousal = f"{int(result.arousal * 100)}%"
    confidence = f"{result.confidence:.0%}"
    flags = []
    if result.pain_mentioned:
        flags.append("Pain-related terms detected")
    if result.distress_mentioned:
        flags.append("Distress-related terms detected")
    flags_text = "\n".join(flags) if flags else "No pain/distress indicators"
    terms = ", ".join(result.key_terms) if result.key_terms else "None"
    return valence, arousal, confidence, flags_text, terms


# ─── Research Content (Markdown) ─────────────────────────────

RESEARCH_TAB1 = """
## Can Emotions Be Reliably Read From Faces?

### The Barrett Critique (2019) -- The Most Important Paper in This Field

> **Barrett, L.F., Adolphs, R., Marsella, S., Martinez, A.M., & Pollak, S.D.** (2019).
> Emotional Expressions Reconsidered: Challenges to Inferring Emotion From Human Facial Movements.
> *Psychological Science in the Public Interest*, 20(1), 1-68. **PMID: 31313636**

**Authors:** Lisa Feldman Barrett (Northeastern/MGH), Ralph Adolphs (Caltech), Stacy Marsella (Northeastern/Glasgow), Aleix M. Martinez (Ohio State), Seth D. Pollak (Wisconsin-Madison)

**What they found** (from verified abstract):

> *"People do sometimes smile when happy, frown when sad, scowl when angry...more than what would be expected by chance. **Yet how people communicate anger, disgust, fear, happiness, sadness, and surprise varies substantially across cultures, situations, and even across people within a single situation.** Furthermore, **similar configurations of facial movements variably express instances of more than one emotion category.**"*

**Key evidence:**
- People scowl during anger only **~30% of the time**
- The same facial configuration (wide eyes, open mouth) is labeled "fear" by Westerners but "threat/aggression" by Trobriand Islanders
- Forced-choice paradigms **inflated** apparent cross-cultural agreement in Ekman's original studies
- fMRI studies show **no consistent neural fingerprint** for any basic emotion category
- The face-to-emotion mapping is **many-to-many**, not one-to-one

**Bottom line:** The assumption underlying all commercial "emotion AI" -- that specific facial expressions reliably map to specific internal emotions -- is **not well-supported** by the totality of scientific evidence.

---

### Coles, Larsen & Lench (2019) -- Meta-Analysis of 138 Studies

> **Coles, N.A., Larsen, J.T., & Lench, H.C.** (2019). A meta-analysis of the facial feedback literature. *Psychological Bulletin*, 145(6), 610-651. **PMID: 30973236**

**Scale:** Meta-analysis of **286 effect sizes** from **138 studies**

- The overall effect of facial expressions on emotional experience was **statistically significant but small**
- Effects were **larger in the absence** of emotionally evocative stimuli
- Publication bias was detected

**Implication:** The face-to-emotion link exists but is **weak and context-dependent**.

---

### Ekman's Universal Emotions (1971) -- The Classical View

| Emotion | Key Facial Indicators |
|---|---|
| **Happiness** | Raised cheeks, crow's feet, lip corners up (Duchenne smile) |
| **Sadness** | Inner brow raised, lip corners down, chin raised |
| **Anger** | Brows lowered & together, eyes glaring, lips tightened |
| **Fear** | Brows raised & together, upper eyelids raised, mouth open |
| **Surprise** | Brows raised, eyes wide open, jaw dropped |
| **Disgust** | Nose wrinkled, upper lip raised, cheeks raised |

**Russell's Circumplex Model** (used in this system) maps emotions on two continuous dimensions: **Valence** (negative-positive) and **Arousal** (calm-excited). This is more scientifically defensible per Barrett's findings.
"""

RESEARCH_TAB2 = """
## Can We Actually Read Thoughts? The Science of Neural Decoding

> **There is a fundamental gap between emotion recognition (detecting affective states) and thought inference (determining cognitive content). Facial expressions may correlate with certain types of cognitive processing but cannot reveal specific thoughts.**

---

### Tang et al. (2023) -- Decoding Language from fMRI

> **Tang, J., LeBel, A., Jain, S., & Huth, A.G.** (2023). Semantic reconstruction of continuous language from non-invasive brain recordings. *Nature Neuroscience*, 26(5), 858-866. **PMID: 37127759**

- 3 participants, 16+ hours of fMRI per subject
- Decoder generates intelligible word sequences recovering **meaning** of perceived/imagined speech
- **Subject cooperation is REQUIRED** -- decoder fails without it
- Captures **semantic gist**, not verbatim thoughts

---

### Willett et al. (2023) -- Speech Neuroprosthesis

> **Willett, F.R., et al.** (2023). A high-performance speech neuroprosthesis. *Nature*, 620(7976), 1031-1036. **PMID: 37612500**

| Metric | Result |
|--------|--------|
| Word error rate (50-word vocab) | **9.1%** (2.7x fewer errors than previous SOTA) |
| Word error rate (125K-word vocab) | **23.8%** |
| Decoding speed | **62 words per minute** (3.4x previous record) |

**Requirement:** Brain surgery to implant intracortical microelectrode arrays.

---

### MindEye: Scotti et al. (2023)

> fMRI + CLIP + Diffusion models to reconstruct images a person is viewing. Requires 7T fMRI and 30-40 hours of per-person training data.
"""

RESEARCH_TAB3 = """
## Evidence-Based Verdict: What Is and Isn't Possible

### Scientifically Supported (Strong Evidence)

| Capability | Key Evidence | Real Accuracy |
|---|---|---|
| **Decoding viewed images** from fMRI | MindEye (NeurIPS 2023) | High semantic fidelity |
| **Decoding semantic gist** of thought | Tang et al. (*Nature Neuroscience*, 2023) | Paraphrase-level |
| **Decoding attempted speech** from implants | Willett et al. (*Nature*, 2023) | 9.1% WER, 62 wpm |
| **Distinguishing genuine vs. fake smiles** | FACS Duchenne vs. Pan-Am | Well-established |
| **Pain detection from faces** (non-verbal) | Prkachin & Solomon PSPI | Clinically validated |
| **Detecting attention direction** (gaze) | Eye tracking / face mesh | Strong evidence |
| **Detecting drowsiness/fatigue** | EAR (Eye Aspect Ratio) | Strong evidence |

### NOT Supported (No Scientific Basis)

| Claim | Status |
|---|---|
| **Reading specific thoughts from faces** | No scientific basis (Barrett et al.) |
| **Reliable deception detection from faces** | Debunked (~54% accuracy, barely above chance) |
| **Predicting criminality from faces** | Pseudoscience |
| **Covert mind reading** | Impossible with current tech |
| **Verbatim thought transcription** | Not achieved |

### Benchmark Accuracy

| Benchmark | SOTA Accuracy | Notes |
|---|---|---|
| RAF-DB | ~92.5% | 7-class expression + landmark |
| AffectNet-7 | ~67.5% | 7-class |
| FER2013 | ~76% | Human agreement only ~65% |
| CK+ | >99% | Saturated; not meaningful |
"""

RESEARCH_TAB4 = """
## Facial Action Coding System (FACS)

Developed by **Paul Ekman and Wallace Friesen (1978)**, FACS decomposes any facial expression into **Action Units (AUs)** -- individual muscle movements.

### Action Units Used in This System

| AU | Name | Muscle | Used For |
|----|------|--------|----------|
| AU1 | Inner Brow Raiser | Frontalis (medial) | Sadness, fear, surprise |
| AU2 | Outer Brow Raiser | Frontalis (lateral) | Surprise, fear |
| AU4 | Brow Lowerer | Corrugator supercilii | **Pain**, anger, concentration |
| AU6 | Cheek Raiser | Orbicularis oculi (orbital) | **Genuine smile**, **pain** |
| AU7 | Lid Tightener | Orbicularis oculi (palpebral) | **Pain**, squinting |
| AU9 | Nose Wrinkler | Levator labii superioris alaeque nasi | Disgust, **pain** |
| AU10 | Upper Lip Raiser | Levator labii superioris | Disgust, **pain** |
| AU12 | Lip Corner Puller | Zygomaticus major | **Smile** |
| AU15 | Lip Corner Depressor | Depressor anguli oris | Sadness |
| AU43 | Eyes Closed | Relaxation of levator palpebrae | **Pain**, sleep |

### Pain Detection: PSPI Scale (Used in This System)

**PSPI = AU4 + max(AU6, AU7) + max(AU9, AU10) + AU43**

| Score Range | Pain Level |
|-------------|------------|
| 0 - 1.5 | None |
| 1.5 - 4.0 | Mild |
| 4.0 - 8.0 | Moderate |
| 8.0 - 16.0 | Severe |

### Duchenne vs. Pan-Am Smile
- **Duchenne smile** (genuine): AU6 + AU12 -- includes crow's feet
- **Pan-Am smile** (fake): Only AU12 -- no crow's feet wrinkles
"""

RESEARCH_TAB5 = """
## Complete Verified Reference List

| # | Citation | Identifier |
|---|---------|------------|
| 1 | Barrett, L.F., et al. (2019). Emotional Expressions Reconsidered. *PSPI*, 20(1), 1-68. | **PMID: 31313636** |
| 2 | Tang, J., et al. (2023). Semantic reconstruction of continuous language from non-invasive brain recordings. *Nature Neuroscience*, 26(5), 858-866. | **PMID: 37127759** |
| 3 | Willett, F.R., et al. (2023). A high-performance speech neuroprosthesis. *Nature*, 620(7976), 1031-1036. | **PMID: 37612500** |
| 4 | Scotti, P.S., et al. (2023). MindEye: fMRI-to-Image with Contrastive Learning. *NeurIPS 2023*. | **arXiv: 2305.18274** |
| 5 | Coles, N.A., et al. (2019). Meta-analysis of facial feedback. *Psych Bulletin*, 145(6), 610-651. | **PMID: 30973236** |
| 6 | Ekman, P. & Friesen, W.V. (1978). *Facial Action Coding System*. | Book |
| 7 | Picard, R.W. (1997). *Affective Computing*. MIT Press. | Book |
| 8 | Prkachin, K.M. (1992). Facial expressions of pain. *Pain*, 51(3), 297-306. | Paper |
| 9 | Lucey, P., et al. (2011). Painful data: UNBC-McMaster pain archive. *IEEE FG*. | Paper |
| 10 | Poh, M.Z., et al. (2010). Non-contact cardiac pulse measurements. *Optics Express*, 18(10). | Paper |
| 11 | Poria, S., et al. (2017). Review of affective computing. *Information Fusion*, 37, 98-125. | Paper |
| 12 | Russell, J.A. (1980). Circumplex model of affect. *JPSP*, 39(6), 1161-1178. | Paper |
| 13 | Schuller, B., et al. (2018). Speech emotion recognition. *Communications of the ACM*. | Paper |

### Key Takeaway

> **Faces reveal emotional displays (not specific thoughts), and actual thought decoding requires
> brain imaging equipment, extensive per-person training, and active cooperation from the subject.
> No technology can read thoughts from facial expressions or covertly from a distance.**
"""

ABOUT_TEXT = """
## Multimodal Patient Care Monitoring System

A scientifically-grounded monitoring tool for caregivers combining multiple modalities.

| Module | Method | Scientific Basis |
|--------|--------|-----------------|
| **Face Analysis** | MediaPipe FaceLandmarker + AU estimation | FACS (Ekman & Friesen, 1978) |
| **Pain Detection** | PSPI scale from AUs | Prkachin & Solomon; Lucey et al. (2011) |
| **Voice Analysis** | Pitch, energy, spectral features | Schuller et al. (2018) |
| **Text Sentiment** | Domain-specific lexicon | Dimensional model (Russell, 1980) |
| **Fusion** | Confidence-weighted late fusion | Poria et al. (2017) |

### Design Principles

1. **No naive emotion labels** -- Per Barrett et al. (2019), facial configurations do NOT reliably map 1:1 to internal emotions. We report Action Units and dimensional states instead.
2. **Privacy-first** -- All processing is local. No video is stored.
3. **Transparent** -- Rule-based methods for explainability. Every threshold has a citation.
4. **Supplement, not replace** -- This system supports clinical judgment, it does not replace it.

### Disclaimer

This system detects facial Action Units and physiological indicators. Per Barrett et al. (2019, PMID: 31313636), facial configurations do NOT reliably map 1:1 to internal emotional states. All outputs should be interpreted as behavioral observations, not definitive diagnoses. Not FDA-approved for clinical use.
"""


# ─── Build Gradio UI ─────────────────────────────────────────

custom_css = """
.metric-box {
    background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
    border: 1px solid #334155;
    border-radius: 12px;
    padding: 16px;
    text-align: center;
}
.metric-box h3 { margin: 0; font-size: 0.85em; color: #94a3b8; }
.metric-box p { margin: 4px 0 0; font-size: 1.6em; font-weight: 700; color: #e2e8f0; }
.disclaimer {
    background: #1e293b;
    border-left: 4px solid #f59e0b;
    padding: 12px 16px;
    border-radius: 0 8px 8px 0;
    margin: 8px 0;
    font-size: 0.9em;
    color: #cbd5e1;
}
"""

with gr.Blocks(
    title="Patient Care Monitor",
    theme=gr.themes.Soft(
        primary_hue="blue",
        secondary_hue="slate",
        neutral_hue="slate",
        font=gr.themes.GoogleFont("Inter"),
    ),
    css=custom_css,
) as demo:

    gr.Markdown(
        "# Patient Care Monitor\n"
        "### Scientifically-grounded multimodal patient monitoring for caregivers"
    )
    gr.HTML(
        '<div class="disclaimer">'
        '<strong>Scientific Disclaimer:</strong> This system detects facial Action Units and '
        'physiological indicators. Per Barrett et al. (2019, PMID: 31313636), facial configurations '
        'do NOT reliably map 1:1 to internal emotional states. All readings are behavioral '
        'observations, not diagnoses.'
        '</div>'
    )

    with gr.Tabs():
        # ── Tab 1: Live Monitor ──
        with gr.Tab("Live Monitor", id="monitor"):
            with gr.Row():
                with gr.Column(scale=3):
                    webcam_input = gr.Image(
                        sources=["webcam"],
                        streaming=True,
                        type="numpy",
                        label="Webcam Feed",
                        mirror_webcam=True,
                    )
                with gr.Column(scale=3):
                    annotated_output = gr.Image(
                        label="Analysis Output",
                        type="numpy",
                        interactive=False,
                    )

            with gr.Row():
                comfort_out = gr.Textbox(label="Comfort", interactive=False, scale=1)
                pain_out = gr.Textbox(label="Pain (PSPI)", interactive=False, scale=1)
                arousal_out = gr.Textbox(label="Arousal", interactive=False, scale=1)
                engagement_out = gr.Textbox(label="Engagement", interactive=False, scale=1)
                face_out = gr.Textbox(label="Face", interactive=False, scale=1)

            details_out = gr.Markdown(label="Details", value="*Waiting for webcam...*")

            webcam_input.stream(
                fn=process_frame,
                inputs=[webcam_input],
                outputs=[annotated_output, comfort_out, pain_out, arousal_out,
                         engagement_out, face_out, details_out],
            )

        # ── Tab 2: Text Analysis ──
        with gr.Tab("Text Analysis", id="text"):
            gr.Markdown("## Caregiver Notes - Text Analysis\nEnter caregiver notes or patient statements to analyze for pain/distress indicators and sentiment.")
            text_input = gr.Textbox(
                label="Enter text",
                placeholder="e.g., Patient complaining of sharp pain in lower back",
                lines=3,
            )
            analyze_btn = gr.Button("Analyze", variant="primary")

            with gr.Row():
                valence_out = gr.Textbox(label="Valence (Positivity)", interactive=False)
                text_arousal_out = gr.Textbox(label="Arousal", interactive=False)
                text_conf_out = gr.Textbox(label="Confidence", interactive=False)

            flags_out = gr.Textbox(label="Pain/Distress Flags", interactive=False, lines=2)
            terms_out = gr.Textbox(label="Key Terms Detected", interactive=False)

            analyze_btn.click(
                fn=analyze_text,
                inputs=[text_input],
                outputs=[valence_out, text_arousal_out, text_conf_out, flags_out, terms_out],
            )

        # ── Tab 3-7: Research ──
        with gr.Tab("Facial Emotion Science", id="r1"):
            gr.Markdown(RESEARCH_TAB1)

        with gr.Tab("Thought Decoding", id="r2"):
            gr.Markdown(RESEARCH_TAB2)

        with gr.Tab("What Works & What Doesn't", id="r3"):
            gr.Markdown(RESEARCH_TAB3)

        with gr.Tab("FACS & Action Units", id="r4"):
            gr.Markdown(RESEARCH_TAB4)

        with gr.Tab("References", id="r5"):
            gr.Markdown(RESEARCH_TAB5)

        with gr.Tab("About", id="about"):
            gr.Markdown(ABOUT_TEXT)


if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=7860)
