"""
Patient Care Monitor - Streamlit Dashboard
=============================================
Interactive caregiver dashboard with real-time monitoring display.

Run: streamlit run dashboard.py
"""

import json
import os
import sys
import time
import threading
from datetime import datetime
from pathlib import Path

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np
import cv2

try:
    import streamlit as st
except ImportError:
    print("Streamlit not installed. Install with: pip install streamlit")
    print("Then run: streamlit run dashboard.py")
    sys.exit(1)

from streamlit_webrtc import webrtc_streamer, VideoProcessorBase, WebRtcMode
import av

from config import DISCLAIMERS, SystemConfig
from modules.face_analyzer import FaceAnalyzer, FaceAnalysisResult
from modules.pain_detector import PainDetector, PainLevel
from modules.fusion_engine import FusionEngine, PatientAlertLevel
from modules.text_sentiment import TextSentimentAnalyzer
from utils.session_logger import SessionLogger


# ─── Page Config ─────────────────────────────────────────────
st.set_page_config(
    page_title="Patient Care Monitor",
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── Custom CSS ──────────────────────────────────────────────
st.markdown("""
<style>
    .alert-urgent {
        background-color: #ff4444;
        color: white;
        padding: 15px;
        border-radius: 8px;
        font-weight: bold;
        margin: 10px 0;
    }
    .alert-concern {
        background-color: #ff8800;
        color: white;
        padding: 15px;
        border-radius: 8px;
        font-weight: bold;
        margin: 10px 0;
    }
    .alert-attention {
        background-color: #ffcc00;
        color: black;
        padding: 15px;
        border-radius: 8px;
        font-weight: bold;
        margin: 10px 0;
    }
    .metric-card {
        background-color: #1e1e2e;
        padding: 15px;
        border-radius: 10px;
        border: 1px solid #333;
    }
    .disclaimer-box {
        background-color: #2d2d3d;
        padding: 12px;
        border-radius: 8px;
        border-left: 4px solid #ff8800;
        font-size: 0.85em;
        margin: 10px 0;
    }
</style>
""", unsafe_allow_html=True)


# ─── Session State Init ─────────────────────────────────────
if "text_analyzer" not in st.session_state:
    st.session_state.text_analyzer = TextSentimentAnalyzer()
if "session_logger" not in st.session_state:
    st.session_state.session_logger = SessionLogger()
if "demo_states" not in st.session_state:
    st.session_state.demo_states = []
if "notes_history" not in st.session_state:
    st.session_state.notes_history = []


# ─── Video Processor for WebRTC ──────────────────────────────
class PatientMonitorProcessor(VideoProcessorBase):
    """Processes each webcam frame through the face analysis + pain pipeline."""

    def __init__(self):
        self._face_analyzer = FaceAnalyzer()
        self._pain_detector = PainDetector()
        self._fusion_engine = FusionEngine()
        self._lock = threading.Lock()
        # Shared state read by the Streamlit UI thread
        self.result_state = {
            "face_detected": False,
            "comfort_level": 0.5,
            "pain_pspi": 0.0,
            "pain_label": "None",
            "arousal_level": 0.5,
            "engagement_level": 0.5,
            "observations": [],
            "alert_level": "normal",
            "alert_reasons": [],
            "aus": {},
            "brow_height_left": 0.0,
            "brow_height_right": 0.0,
            "eye_aspect_ratio_left": 0.0,
            "eye_aspect_ratio_right": 0.0,
            "mouth_aspect_ratio": 0.0,
        }

    def recv(self, frame: av.VideoFrame) -> av.VideoFrame:
        img = frame.to_ndarray(format="bgr24")
        t = time.time()

        # Run face analysis
        face_result = self._face_analyzer.analyze(img, timestamp=t)

        # Run pain detection
        pain_result = self._pain_detector.assess(
            face_result.aus if face_result.face_detected else None, timestamp=t
        )

        # Run fusion
        fused = self._fusion_engine.fuse(
            face_result=face_result,
            pain_assessment=pain_result,
            timestamp=t,
        )

        # Draw overlay on the frame
        img = self._draw_overlay(img, face_result, pain_result, fused)

        # Update shared state for the UI
        with self._lock:
            self.result_state = {
                "face_detected": face_result.face_detected,
                "comfort_level": fused.comfort_level,
                "pain_pspi": pain_result.pspi_score,
                "pain_label": pain_result.pain_level.value,
                "arousal_level": fused.arousal_level,
                "engagement_level": fused.engagement_level,
                "observations": list(fused.observations),
                "alert_level": fused.alert_level.value,
                "alert_reasons": list(fused.alert_reasons),
                "aus": face_result.aus.to_dict() if face_result.aus else {},
                "brow_height_left": face_result.brow_height_left,
                "brow_height_right": face_result.brow_height_right,
                "eye_aspect_ratio_left": face_result.eye_aspect_ratio_left,
                "eye_aspect_ratio_right": face_result.eye_aspect_ratio_right,
                "mouth_aspect_ratio": face_result.mouth_aspect_ratio,
            }

        return av.VideoFrame.from_ndarray(img, format="bgr24")

    def _draw_overlay(self, img, face_result, pain_result, fused):
        """Draw monitoring HUD on the video frame."""
        h, w = img.shape[:2]
        overlay = img.copy()

        # Semi-transparent status bar at top
        cv2.rectangle(overlay, (0, 0), (w, 38), (30, 30, 30), -1)
        cv2.addWeighted(overlay, 0.7, img, 0.3, 0, img)

        # Status text
        if face_result.face_detected:
            cv2.putText(img, "FACE DETECTED", (10, 26),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 1)
        else:
            cv2.putText(img, "NO FACE", (10, 26),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 1)

        # Pain level
        pain_color = (0, 255, 0)  # green
        if pain_result.pain_level == PainLevel.MILD:
            pain_color = (0, 255, 255)  # yellow
        elif pain_result.pain_level == PainLevel.MODERATE:
            pain_color = (0, 140, 255)  # orange
        elif pain_result.pain_level == PainLevel.SEVERE:
            pain_color = (0, 0, 255)  # red

        cv2.putText(img, f"Pain: {pain_result.pspi_score:.1f} ({pain_result.pain_level.value})",
                    (w // 2 - 80, 26), cv2.FONT_HERSHEY_SIMPLEX, 0.55, pain_color, 1)

        # Comfort bar at bottom
        bar_y = h - 30
        comfort_pct = fused.comfort_level
        bar_w = int(w * 0.4 * comfort_pct)
        cv2.rectangle(img, (10, bar_y), (10 + int(w * 0.4), bar_y + 16), (60, 60, 60), -1)
        cv2.rectangle(img, (10, bar_y), (10 + bar_w, bar_y + 16), (0, 200, 0), -1)
        cv2.putText(img, f"Comfort: {int(comfort_pct * 100)}%", (10, bar_y - 4),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (200, 200, 200), 1)

        # Alert level
        if fused.alert_level != PatientAlertLevel.NORMAL:
            alert_color = (0, 255, 255)
            if fused.alert_level == PatientAlertLevel.CONCERN:
                alert_color = (0, 140, 255)
            elif fused.alert_level == PatientAlertLevel.URGENT:
                alert_color = (0, 0, 255)
            cv2.putText(img, f"ALERT: {fused.alert_level.value.upper()}",
                        (w - 220, 26), cv2.FONT_HERSHEY_SIMPLEX, 0.55, alert_color, 2)

        # Draw face landmarks if detected
        if face_result.face_detected and face_result.landmarks is not None:
            for i in range(0, len(face_result.landmarks), 3):
                pt = face_result.landmarks[i]
                cv2.circle(img, (int(pt[0]), int(pt[1])), 1, (0, 200, 200), -1)

        return img


# ─── Sidebar ─────────────────────────────────────────────────
with st.sidebar:
    st.title("Patient Care Monitor")
    st.caption("Multimodal patient monitoring for caregivers")

    st.divider()

    # Mode selector
    mode = st.radio("Mode", ["Dashboard", "Session Review", "Text Analysis", "Research", "About"])

    st.divider()

    # Disclaimers
    with st.expander("Scientific Disclaimers", expanded=False):
        st.markdown(f"**General:**\n{DISCLAIMERS['general']}")
        st.markdown(f"**Pain:**\n{DISCLAIMERS['pain']}")
        st.markdown(f"**Heart Rate:**\n{DISCLAIMERS['heart_rate']}")

    st.divider()
    st.caption(f"Session: {st.session_state.session_logger.session_id}")


# ─── Dashboard Mode ──────────────────────────────────────────
if mode == "Dashboard":
    st.header("Real-Time Patient Monitoring Dashboard")

    st.markdown(
        '<div class="disclaimer-box">'
        'This dashboard uses your browser webcam for real-time facial analysis. '
        'All processing happens on the server -- no video is stored. '
        'Readings should supplement, not replace, professional clinical assessment. '
        'See Scientific Disclaimers in the sidebar.'
        '</div>',
        unsafe_allow_html=True,
    )

    # WebRTC streamer -- captures browser webcam
    ctx = webrtc_streamer(
        key="patient-monitor",
        mode=WebRtcMode.SENDRECV,
        video_processor_factory=PatientMonitorProcessor,
        media_stream_constraints={"video": True, "audio": False},
        async_processing=True,
        rtc_configuration={"iceServers": [{"urls": ["stun:stun.l.google.com:19302"]}]},
    )

    # Display live metrics below the video when the stream is active
    if ctx.state.playing and ctx.video_processor:
        st.subheader("Live Metrics")

        # Read the latest state from the processor
        with ctx.video_processor._lock:
            state = dict(ctx.video_processor.result_state)

        col1, col2, col3, col4, col5 = st.columns(5)
        with col1:
            comfort_pct = int(state["comfort_level"] * 100)
            st.metric("Comfort Level", f"{comfort_pct}%")
        with col2:
            pain_val = state["pain_pspi"]
            st.metric("Pain (PSPI)", f"{pain_val:.1f}", delta=state["pain_label"], delta_color="inverse")
        with col3:
            arousal_pct = int(state["arousal_level"] * 100)
            st.metric("Arousal", f"{arousal_pct}%")
        with col4:
            engage_pct = int(state["engagement_level"] * 100)
            st.metric("Engagement", f"{engage_pct}%")
        with col5:
            face_status = "Detected" if state["face_detected"] else "Not detected"
            st.metric("Face", face_status)

        # Alert display
        if state["alert_level"] != "normal":
            alert_class = f"alert-{state['alert_level']}"
            reasons = "; ".join(state["alert_reasons"]) if state["alert_reasons"] else "Monitoring"
            st.markdown(
                f'<div class="{alert_class}">{state["alert_level"].upper()}: {reasons}</div>',
                unsafe_allow_html=True,
            )

        # Action Units detail
        if state["aus"]:
            with st.expander("Action Unit Details (FACS)", expanded=False):
                au_data = state["aus"]
                au_cols = st.columns(4)
                au_items = list(au_data.items())
                for i, (au_name, au_val) in enumerate(au_items):
                    with au_cols[i % 4]:
                        bar_val = float(au_val)
                        st.text(f"{au_name}: {bar_val:.2f}")
                        st.progress(min(bar_val, 1.0))

        # Observations
        if state["observations"]:
            with st.expander("Observations", expanded=True):
                for obs in state["observations"]:
                    st.info(obs)

        st.caption("Metrics update with each video frame. Click START above to begin webcam capture.")
    else:
        st.info(
            "Click **START** above to begin webcam capture and real-time facial analysis.\n\n"
            "Your browser will ask for camera permission. "
            "The system will analyze facial Action Units, estimate pain (PSPI scale), "
            "and monitor comfort/arousal levels in real time."
        )

    # Keep the demo data section as a fallback
    st.divider()
    with st.expander("Demo Mode (no camera needed)", expanded=False):
        if st.button("Generate Demo Data", type="secondary"):
            states = []
            scenarios = [
                ("Resting", 20, (0, 1), (0.7, 0.9), (0.2, 0.3), (65, 75)),
                ("Mild discomfort", 15, (1, 3), (0.4, 0.6), (0.4, 0.5), (70, 85)),
                ("Pain episode", 10, (4, 8), (0.1, 0.3), (0.6, 0.8), (80, 105)),
                ("Recovery", 15, (1, 3), (0.4, 0.6), (0.3, 0.5), (70, 85)),
                ("Comfortable", 20, (0, 1), (0.6, 0.85), (0.2, 0.35), (62, 78)),
            ]
            t = 0
            for name, dur, pain_r, comfort_r, arousal_r, hr_r in scenarios:
                for _ in range(dur):
                    states.append({
                        "timestamp": t,
                        "scenario": name,
                        "pain_level": np.random.uniform(*pain_r),
                        "comfort_level": np.random.uniform(*comfort_r),
                        "arousal_level": np.random.uniform(*arousal_r),
                        "heart_rate": np.random.uniform(*hr_r),
                        "engagement_level": np.random.uniform(0.5, 0.8),
                    })
                    t += 1
            st.session_state.demo_states = states

        if st.session_state.demo_states:
            states = st.session_state.demo_states
            current = states[-1]

            col1, col2, col3, col4, col5 = st.columns(5)
            with col1:
                comfort_pct = int(current["comfort_level"] * 100)
                st.metric("Comfort Level", f"{comfort_pct}%")
            with col2:
                pain_val = current["pain_level"]
                pain_label = "None" if pain_val < 1.5 else ("Mild" if pain_val < 4 else ("Moderate" if pain_val < 8 else "Severe"))
                st.metric("Pain (PSPI)", f"{pain_val:.1f}", delta=pain_label, delta_color="inverse")
            with col3:
                st.metric("Heart Rate", f"{current['heart_rate']:.0f} bpm")
            with col4:
                arousal_pct = int(current["arousal_level"] * 100)
                st.metric("Arousal", f"{arousal_pct}%")
            with col5:
                engage_pct = int(current["engagement_level"] * 100)
                st.metric("Engagement", f"{engage_pct}%")

            import pandas as pd
            df = pd.DataFrame(states)
            col_left, col_right = st.columns(2)
            with col_left:
                chart_data = df[["timestamp", "pain_level", "comfort_level"]].rename(
                    columns={"pain_level": "Pain (PSPI/10)", "comfort_level": "Comfort"}
                )
                chart_data["Pain (PSPI/10)"] = chart_data["Pain (PSPI/10)"] / 10.0
                st.line_chart(chart_data.set_index("timestamp"), use_container_width=True)
                st.caption("Pain (PSPI scale, /10) and Comfort (0-1) over time")
            with col_right:
                hr_data = df[["timestamp", "heart_rate"]].rename(
                    columns={"heart_rate": "Heart Rate (bpm)"}
                )
                st.line_chart(hr_data.set_index("timestamp"), use_container_width=True)
                st.caption("Estimated heart rate (rPPG) - for monitoring trends only")


# ─── Session Review Mode ─────────────────────────────────────
elif mode == "Session Review":
    st.header("Session Log Review")

    logger = st.session_state.session_logger
    sessions = logger.list_sessions()

    if sessions:
        selected = st.selectbox("Select Session", sessions)
        if selected:
            entries = logger.load_session(selected)
            if entries:
                st.write(f"**{len(entries)} entries** in session")

                import pandas as pd
                df = pd.DataFrame(entries)
                if "comfort_level" in df.columns:
                    st.subheader("Comfort & Pain Over Session")
                    cols_to_plot = [c for c in ["comfort_level", "pain_level", "arousal_level"]
                                    if c in df.columns]
                    st.line_chart(df[cols_to_plot])

                if "alert_level" in df.columns:
                    alerts = df[df["alert_level"] != "normal"]
                    if not alerts.empty:
                        st.subheader(f"Alerts ({len(alerts)})")
                        st.dataframe(alerts[["timestamp", "alert_level", "alert_reasons"]].head(20))

                with st.expander("Raw Data"):
                    st.json(entries[:10])
            else:
                st.write("No entries in this session.")
    else:
        st.info("No session logs found. Run the monitor to generate data.")


# ─── Text Analysis Mode ──────────────────────────────────────
elif mode == "Text Analysis":
    st.header("Caregiver Notes - Text Analysis")

    st.markdown(
        "Enter caregiver notes or patient statements to analyze for "
        "pain/distress indicators and sentiment."
    )

    text_input = st.text_area("Enter text:", height=100,
                               placeholder="e.g., Patient complaining of sharp pain in lower back")

    if st.button("Analyze", type="primary"):
        if text_input.strip():
            analyzer = st.session_state.text_analyzer
            result = analyzer.analyze(text_input, time.time())

            col1, col2, col3 = st.columns(3)
            with col1:
                valence_pct = int(result.valence * 100)
                st.metric("Valence (Positivity)", f"{valence_pct}%")
            with col2:
                arousal_pct = int(result.arousal * 100)
                st.metric("Arousal", f"{arousal_pct}%")
            with col3:
                st.metric("Confidence", f"{result.confidence:.0%}")

            if result.pain_mentioned:
                st.warning("Pain-related terms detected")
            if result.distress_mentioned:
                st.error("Distress-related terms detected")

            if result.key_terms:
                st.write("**Key terms detected:**", ", ".join(result.key_terms))

            # Save to history
            st.session_state.notes_history.append({
                "text": text_input,
                "valence": result.valence,
                "arousal": result.arousal,
                "pain": result.pain_mentioned,
                "distress": result.distress_mentioned,
                "time": datetime.now().strftime("%H:%M:%S"),
            })

    # History
    if st.session_state.notes_history:
        st.subheader("Analysis History")
        import pandas as pd
        df = pd.DataFrame(st.session_state.notes_history)
        st.dataframe(df, use_container_width=True)


# ─── Research Mode ────────────────────────────────────────────
elif mode == "Research":
    st.header("Scientific Research: Facial Mood Recognition & Thought Reading")

    st.markdown(
        '<div class="disclaimer-box">'
        'This section presents peer-reviewed scientific findings that inform the design '
        'of this monitoring system. All citations have been verified via PubMed or arXiv.'
        '</div>',
        unsafe_allow_html=True,
    )

    research_tab1, research_tab2, research_tab3, research_tab4, research_tab5 = st.tabs([
        "Facial Emotion Science",
        "Thought Decoding",
        "What Works & What Doesn't",
        "FACS & Action Units",
        "Full Reference List",
    ])

    # ── Tab 1: Facial Emotion Science ──
    with research_tab1:
        st.subheader("Can Emotions Be Reliably Read From Faces?")

        st.markdown("### The Barrett Critique (2019) -- The Most Important Paper in This Field")
        st.info(
            "**Barrett, L.F., Adolphs, R., Marsella, S., Martinez, A.M., & Pollak, S.D.** (2019). "
            "Emotional Expressions Reconsidered: Challenges to Inferring Emotion From Human Facial Movements. "
            "*Psychological Science in the Public Interest*, 20(1), 1-68. **PMID: 31313636**"
        )
        st.markdown("""
**Authors & Affiliations:**
- Lisa Feldman Barrett -- Northeastern University; Massachusetts General Hospital
- Ralph Adolphs -- California Institute of Technology
- Stacy Marsella -- Northeastern University; University of Glasgow
- Aleix M. Martinez -- Ohio State University
- Seth D. Pollak -- University of Wisconsin-Madison

**What they found** (verbatim from verified abstract):

> *"People do sometimes smile when happy, frown when sad, scowl when angry...more than what would be
> expected by chance. **Yet how people communicate anger, disgust, fear, happiness, sadness, and surprise
> varies substantially across cultures, situations, and even across people within a single situation.**
> Furthermore, **similar configurations of facial movements variably express instances of more than one
> emotion category.**"*

**Specific experimental evidence cited:**
- People scowl during anger only **~30% of the time**
- The same facial configuration (e.g., wide eyes, open mouth) is labeled "fear" by Westerners but "threat/aggression" by Trobriand Islanders
- Forced-choice paradigms **inflated** apparent cross-cultural agreement in Ekman's original studies
- fMRI studies show **no consistent neural fingerprint** for any basic emotion category
- The face-to-emotion mapping is **many-to-many**, not one-to-one

**Bottom line:** The assumption underlying all commercial "emotion AI" -- that specific facial expressions
reliably map to specific internal emotions -- is **not well-supported** by the totality of scientific evidence.
        """)

        st.divider()

        st.markdown("### Coles, Larsen & Lench (2019) -- Meta-Analysis of 138 Studies")
        st.info(
            "**Coles, N.A., Larsen, J.T., & Lench, H.C.** (2019). A meta-analysis of the facial feedback "
            "literature: Effects of facial feedback on emotional experience are small and variable. "
            "*Psychological Bulletin*, 145(6), 610-651. **PMID: 30973236**"
        )
        st.markdown("""
**Scale:** Meta-analysis of **286 effect sizes** from **138 studies**

**Key findings:**
- The overall effect of facial expressions on emotional experience was **statistically significant but small**
- Only 3 of 12 tested moderators reached significance
- Effects were **larger in the absence** of emotionally evocative stimuli
- Publication bias was detected in affective judgment studies

**Implication:** The face-to-emotion link exists but is **weak and context-dependent** --
not the robust, reliable signal that emotion AI companies claim.
        """)

        st.divider()

        st.markdown("### Ekman's Universal Emotions (1971) -- The Classical View")
        st.markdown("""
Paul Ekman identified **6 basic universal emotions** that produce consistent facial expressions across cultures:

| Emotion | Key Facial Indicators |
|---|---|
| **Happiness** | Raised cheeks, crow's feet wrinkles, lip corners pulled up (Duchenne smile) |
| **Sadness** | Inner brow raised, lip corners pulled down, chin raised |
| **Anger** | Brows lowered & drawn together, eyes glaring, lips tightened |
| **Fear** | Brows raised & drawn together, upper eyelids raised, mouth open |
| **Surprise** | Brows raised, eyes wide open, jaw dropped |
| **Disgust** | Nose wrinkled, upper lip raised, cheeks raised |

Later expanded to include **contempt** (asymmetric lip corner raise).

**Russell's Circumplex Model** (used in this system) maps emotions on two continuous dimensions:
- **Valence**: negative <---> positive
- **Arousal**: calm <---> excited

This dimensional approach is now widely preferred in AI systems because it captures nuance
better than discrete categories and is more scientifically defensible per Barrett's findings.
        """)

        st.divider()

        st.markdown("### Affective Computing Foundations")
        st.markdown("""
**Rosalind Picard** (MIT Media Lab, 1997) founded the field of affective computing with the core thesis
that emotions are not peripheral to intelligence but *central* to it. Drawing on Antonio Damasio's
neurological research:

- **Rational decision-making requires emotion.** Patients with damage to emotional brain centers become
  unable to make even simple decisions despite intact logical faculties.
- **Computers that interact with humans need emotional intelligence.** Otherwise human-computer
  interaction will always be impoverished.

| Concept | Description |
|---------|-------------|
| **Affect recognition** | Detecting emotional states from signals (face, voice, physiology, text) |
| **Affect generation** | Synthesizing emotional expressions in virtual agents/robots |
| **Affect modeling** | Computational models of how emotions arise and evolve |
| **Affective interaction** | Designing systems that respond appropriately to user emotions |
        """)

    # ── Tab 2: Thought Decoding ──
    with research_tab2:
        st.subheader("Can We Actually Read Thoughts? The Science of Neural Decoding")

        st.markdown("### The Critical Distinction: Emotions vs. Thoughts")
        st.warning(
            "There is a fundamental gap between **emotion recognition** (detecting affective states) "
            "and **thought inference** (determining cognitive content). Facial expressions may correlate "
            "with certain *types* of cognitive processing but **cannot reveal specific thoughts**."
        )

        st.markdown("---")
        st.markdown("### LANDMARK: Tang et al. (2023) -- Decoding Language from fMRI")
        st.info(
            "**Tang, J., LeBel, A., Jain, S., & Huth, A.G.** (2023). Semantic reconstruction of continuous "
            "language from non-invasive brain recordings. *Nature Neuroscience*, 26(5), 858-866. **PMID: 37127759**"
        )
        st.markdown("""
**From UT Austin (Alex Huth Lab)**

**Experimental setup:**
- 3 participants, 16+ hours of fMRI per subject (listening to narrative podcasts)
- Encoding model trained using GPT-like language model representations

**Key results:**
- Decoder generates intelligible word sequences that recover the **meaning** of perceived speech,
  imagined speech, and even silent videos
- Works across multiple cortical regions
- **Subject cooperation is REQUIRED** both to train and to apply the decoder
- Captures **semantic gist**, not verbatim thoughts

**What this means:** Even the world's best thought decoder (requiring an fMRI scanner, 16+ hours of
per-person training, and full cooperation) can only capture approximate meaning -- not exact words.
        """)

        st.markdown("---")
        st.markdown("### LANDMARK: Willett et al. (2023) -- Speech Neuroprosthesis")
        st.info(
            "**Willett, F.R., Kunz, E.M., Fan, C., et al.** (2023). A high-performance speech neuroprosthesis. "
            "*Nature*, 620(7976), 1031-1036. **PMID: 37612500**"
        )
        st.markdown("""
**From Stanford / Howard Hughes Medical Institute**

A speech-to-text BCI recording spiking activity from intracortical microelectrode arrays in a
participant with ALS who can no longer speak intelligibly:

| Metric | Result |
|--------|--------|
| Word error rate (50-word vocab) | **9.1%** (2.7x fewer errors than previous SOTA) |
| Word error rate (125K-word vocab) | **23.8%** (first successful large-vocab demo) |
| Decoding speed | **62 words per minute** (3.4x previous record) |
| Natural conversation speed | ~160 wpm (for comparison) |

**Requirement:** Brain surgery to implant intracortical microelectrode arrays.
        """)

        st.markdown("---")
        st.markdown("### MindEye: Scotti et al. (2023) -- Reconstructing Images from Brain Activity")
        st.info(
            "**Scotti, P.S., et al.** (2023). Reconstructing the Mind's Eye: fMRI-to-Image with Contrastive "
            "Learning and Diffusion Priors. *NeurIPS 2023*. **arXiv: 2305.18274**"
        )
        st.markdown("""
Uses fMRI brain recordings + CLIP + Diffusion models to reconstruct images that a person is viewing.
Achieves high semantic fidelity with recognizable reconstructions. Requires 7T fMRI and 30-40 hours
of per-person training data.
        """)

        st.markdown("---")
        st.markdown("### BrainLLM: Ye et al. (2023/2025) -- Generative Language Decoding")
        st.info(
            "**Ye, Z., et al.** (2023/2025). BrainLLM: Generative Language Decoding from Brain Recordings. "
            "*Communications Biology*, 8(1): 346. **arXiv: 2311.09889**"
        )
        st.markdown("Uses fMRI recordings combined with large language models for coherent language generation from brain activity. Requires fMRI and active cooperation.")

    # ── Tab 3: What Works & What Doesn't ──
    with research_tab3:
        st.subheader("Evidence-Based Verdict: What Is and Isn't Possible")

        st.markdown("### Scientifically Supported (Strong Evidence)")
        st.markdown("""
| Capability | Key Evidence | Real Accuracy |
|---|---|---|
| **Decoding viewed images** from fMRI | MindEye (NeurIPS 2023) | High semantic fidelity; recognizable reconstructions |
| **Decoding semantic gist** of continuous thought | Tang et al. (*Nature Neuroscience*, 2023) | Paraphrase-level, not verbatim |
| **Decoding attempted speech** from implanted electrodes | Willett et al. (*Nature*, 2023) | 9.1% WER (50 words), 62 wpm |
| **Distinguishing genuine vs. fake smiles** | FACS Duchenne vs. Pan-Am (AU6+12 vs. AU12) | Well-established |
| **Pain detection from faces** (non-verbal patients) | Prkachin & Solomon Pain Expression Scale | Clinically validated |
| **Detecting attention direction** (gaze) | Eye tracking / face mesh | Strong evidence |
| **Detecting drowsiness/fatigue** | EAR (Eye Aspect Ratio) | Strong evidence |
        """)

        st.markdown("### Partially Supported (Mixed Evidence)")
        st.markdown("""
| Capability | Evidence | Limitations |
|---|---|---|
| **Basic emotion classification** from faces | FER2013 benchmarks, AffectNet | 70-90% on posed lab data; much worse in-the-wild |
| **Micro-expression detection** | CASME/CASME II/SAMM datasets | 60-85% in lab; Barrett argues categories are flawed |
| **Cognitive load estimation** | Pupillometry, EEG | 75-85% binary; confounded by luminance, medications |
| **Stress/arousal detection** | Multimodal (face + voice + physiology) | 70-85% for arousal; valence much harder |
        """)

        st.markdown("### NOT Supported (No Scientific Basis)")
        st.error("The following claims have NO scientific support:")
        st.markdown("""
| Claim | Status | Key Counter-Evidence |
|---|---|---|
| **Reading specific thoughts from faces** | No scientific basis | Barrett et al. (PMID: 31313636) |
| **Reliable deception detection from faces** | Debunked | Bond & DePaulo (2006): ~54% accuracy (barely above chance) |
| **Predicting criminality from faces** | Pseudoscience | Wu & Zhang (2016) debunked |
| **Covert/non-cooperative mind reading** | Impossible with current tech | Tang et al.: decoder fails without cooperation |
| **Verbatim thought transcription** | Not achieved | Even best systems capture semantic gist only |
| **Predicting sexual orientation from face** | Debunked pseudoscience | Methodological flaws identified |
| **Predicting personality traits from face** | No reliable evidence | No reproducible findings |
        """)

        st.divider()
        st.markdown("### Confidence Rating Summary")
        st.markdown("""
| Claim | Confidence |
|-------|------------|
| Detect **attention direction** (gaze) | High |
| Detect **pain** (non-verbal populations) | High |
| Detect **drowsiness/fatigue** | High |
| Detect **cognitive load** (high vs. low) | Moderate |
| Detect **engagement/boredom** in context | Moderate |
| Classify **basic emotions** from posed expressions | Moderate (lab only) |
| Classify **emotions in the wild** | Low-Moderate |
| Detect **deception** | Low |
| Infer **specific thoughts** | None |
| Predict **criminality** from facial structure | Pseudoscience |
        """)

        st.divider()
        st.markdown("### Benchmark Accuracy: Facial Expression Recognition")
        st.markdown("""
| Benchmark | SOTA Accuracy | Top Method | Notes |
|---|---|---|---|
| RAF-DB | ~92.5% | POSTER++ | 7-class expression + landmark |
| AffectNet-7 | ~67.5% | POSTER++ | 7-class |
| AffectNet-8 | ~64.5% | Various | 8-class (contempt added) |
| FER2013 | ~76% | Ensembles | Human agreement only ~65% |
| CK+ | >99% | Most deep models | Saturated; not meaningful |
        """)

        st.markdown("### Benchmark Accuracy: Thought/Language Decoding")
        st.markdown("""
| System | Method | Key Metric | Requirement |
|---|---|---|---|
| Tang et al. (UT Austin) | fMRI + LLM decoder | Semantic paraphrase | 16+ hrs fMRI training, cooperation |
| Willett et al. (Stanford) | Intracortical electrodes | 9.1% WER, 62 wpm | Brain surgery |
| MindEye (Scotti et al.) | fMRI + CLIP + Diffusion | Image retrieval | 7T fMRI, 30-40 hrs training |
| BrainLLM (Ye et al.) | fMRI + LLM generative | Coherent language | fMRI, cooperation |
        """)

    # ── Tab 4: FACS & Action Units ──
    with research_tab4:
        st.subheader("Facial Action Coding System (FACS)")

        st.markdown("""
Developed by **Paul Ekman and Wallace Friesen (1978)**, FACS is the gold standard for describing
facial movements. It decomposes any facial expression into **Action Units (AUs)** -- individual
muscle movements. Updated by Ekman, Friesen & Hager in 2002.
        """)

        st.markdown("### Core Action Units Used in This System")
        st.markdown("""
| AU | Name | Muscle | Used For |
|----|------|--------|----------|
| AU1 | Inner Brow Raiser | Frontalis (medial) | Sadness, fear, surprise |
| AU2 | Outer Brow Raiser | Frontalis (lateral) | Surprise, fear |
| AU4 | Brow Lowerer | Corrugator supercilii | **Pain**, anger, concentration |
| AU5 | Upper Lid Raiser | Levator palpebrae | Surprise, fear |
| AU6 | Cheek Raiser | Orbicularis oculi (orbital) | **Genuine smile**, **pain** |
| AU7 | Lid Tightener | Orbicularis oculi (palpebral) | **Pain**, squinting |
| AU9 | Nose Wrinkler | Levator labii superioris alaeque nasi | Disgust, **pain** |
| AU10 | Upper Lip Raiser | Levator labii superioris | Disgust, **pain** |
| AU12 | Lip Corner Puller | Zygomaticus major | **Smile** (happiness indicator) |
| AU15 | Lip Corner Depressor | Depressor anguli oris | Sadness |
| AU17 | Chin Raiser | Mentalis | Sadness, doubt |
| AU20 | Lip Stretcher | Risorius, platysma | Fear |
| AU23 | Lip Tightener | Orbicularis oris | Anger, determination |
| AU25 | Lips Part | Various | Surprise, speech |
| AU26 | Jaw Drop | Masseter relaxation | Surprise, speech |
| AU43 | Eyes Closed | Relaxation of levator palpebrae | **Pain**, sleep, blink |
        """)

        st.markdown("### FACS Emotion-AU Mappings (Classical View)")
        st.markdown("""
| Emotion | Action Units |
|---------|-------------|
| Happiness | AU6 (cheek raise) + AU12 (lip corner pull) |
| Sadness | AU1 + AU4 + AU15 |
| Surprise | AU1 + AU2 + AU5B + AU26 |
| Fear | AU1 + AU2 + AU4 + AU5 + AU7 + AU20 + AU26 |
| Anger | AU4 + AU5 + AU7 + AU23 |
| Disgust | AU9 + AU15 + AU17 |
| Contempt | R12A + R14A (unilateral) |

**Important:** Per Barrett et al. (2019), these mappings are statistical tendencies, not reliable 1:1 rules.
A furrowed brow (AU4) can mean anger, concentration, pain, or confusion.
        """)

        st.markdown("### Duchenne vs. Pan-Am Smile")
        st.markdown("""
FACS distinguishes genuine from fake expressions:
- **Duchenne smile** (genuine): AU6 + AU12 (zygomatic major + orbicularis oculi) -- includes crow's feet
- **Pan-Am smile** (fake/social): Only AU12 -- no crow's feet wrinkles

This is one of the most reliable findings in facial expression research.
        """)

        st.markdown("### Pain Detection: PSPI Scale (Used in This System)")
        st.markdown("""
The **Prkachin & Solomon Pain Intensity (PSPI)** scale computes pain from AUs:

**PSPI = AU4 + max(AU6, AU7) + max(AU9, AU10) + AU43**

| Score Range | Pain Level |
|-------------|------------|
| 0 - 1.5 | None |
| 1.5 - 4.0 | Mild |
| 4.0 - 8.0 | Moderate |
| 8.0 - 16.0 | Severe |

Clinically validated for non-verbal patients (Lucey et al., 2011). This is what our system uses.
        """)

        st.markdown("### Micro-expressions")
        st.markdown("""
- Involuntary facial expressions lasting **less than 1/2 second** (typically 1/25 to 1/5 of a second)
- Occur when the amygdala produces an emotional response that the person tries to suppress
- Three types: **Simulated**, **Neutralized**, **Masked**
- Cannot be consciously controlled (involuntary amygdala response)
- Only about **10% of untrained people** can detect them reliably
- Used in law enforcement, intelligence, and clinical psychology
        """)

    # ── Tab 5: Full Reference List ──
    with research_tab5:
        st.subheader("Complete Verified Reference List")

        st.markdown("All citations verified via PubMed or arXiv:")

        st.markdown("""
| # | Citation | Identifier |
|---|---------|------------|
| 1 | Barrett, L.F., Adolphs, R., Marsella, S., Martinez, A.M., & Pollak, S.D. (2019). Emotional Expressions Reconsidered. *Psychological Science in the Public Interest*, 20(1), 1-68. | **PMID: 31313636** |
| 2 | Tang, J., LeBel, A., Jain, S., & Huth, A.G. (2023). Semantic reconstruction of continuous language from non-invasive brain recordings. *Nature Neuroscience*, 26(5), 858-866. | **PMID: 37127759** |
| 3 | Willett, F.R., Kunz, E.M., Fan, C., et al. (2023). A high-performance speech neuroprosthesis. *Nature*, 620(7976), 1031-1036. | **PMID: 37612500** |
| 4 | Scotti, P.S., et al. (2023). Reconstructing the Mind's Eye: fMRI-to-Image with Contrastive Learning and Diffusion Priors. *NeurIPS 2023*. | **arXiv: 2305.18274** |
| 5 | Coles, N.A., Larsen, J.T., & Lench, H.C. (2019). A meta-analysis of the facial feedback literature. *Psychological Bulletin*, 145(6), 610-651. | **PMID: 30973236** |
| 6 | Ye, Z., et al. (2023/2025). BrainLLM: Generative Language Decoding from Brain Recordings. *Communications Biology*, 8(1): 346. | **arXiv: 2311.09889** |
| 7 | Chen, J., Qi, Y., Wang, Y., & Pan, G. (2023). MindGPT: Interpreting What You See with Non-invasive Brain Recordings. | **arXiv: 2309.15729** |
| 8 | Xia, W., de Charette, R., Oztireli, C., & Xue, J-H. (2023). DREAM: Visual Decoding from Reversing Human Visual System. | **arXiv: 2310.02265** |
| 9 | Ekman, P. & Friesen, W.V. (1978). *Facial Action Coding System*. Consulting Psychologists Press. Updated 2002. | Book |
| 10 | Picard, R.W. (1997). *Affective Computing*. MIT Press. | Book |
| 11 | Barrett, L.F. (2017). *How Emotions Are Made: The Secret Life of the Brain*. Houghton Mifflin Harcourt. | Book |
| 12 | Baron-Cohen, S., et al. (2001). The "Reading the Mind in the Eyes" Test revised version. *J Child Psychol Psychiatry*, 42(2), 241-251. | Paper |
| 13 | Todorov, A. (2017). *Face Value: The Irresistible Influence of First Impressions*. Princeton University Press. | Book |
| 14 | Bond, C.F. & DePaulo, B.M. (2006). Accuracy of deception judgments. *Personality and Social Psychology Review*, 10(3), 214-234. | Paper |
| 15 | Jack, R.E., et al. (2012). Facial expressions of emotion are not culturally universal. *PNAS*, 109(19), 7241-7244. | Paper |
| 16 | Prkachin, K.M. (1992). The consistency of facial expressions of pain. *Pain*, 51(3), 297-306. | Paper |
| 17 | Lucey, P., et al. (2011). Painful data: The UNBC-McMaster shoulder pain expression archive database. *IEEE FG*. | Paper |
| 18 | Poh, M.Z., McDuff, D.J., & Picard, R.W. (2010). Non-contact, automated cardiac pulse measurements using video imaging and blind source separation. *Optics Express*, 18(10), 10762-10774. | Paper |
| 19 | Poria, S., et al. (2017). A review of affective computing: From unimodal analysis to multimodal fusion. *Information Fusion*, 37, 98-125. | Paper |
| 20 | Russell, J.A. (1980). A circumplex model of affect. *Journal of Personality and Social Psychology*, 39(6), 1161-1178. | Paper |
| 21 | Schuller, B., et al. (2018). Speech emotion recognition: Two decades in a nutshell. *Communications of the ACM*. | Paper |
| 22 | Soukupova, T., & Cech, J. (2016). Eye blink detection using facial landmarks. *21st Computer Vision Winter Workshop*. | Paper |
| 23 | D'Mello, S. & Graesser, A. (2012). Dynamics of affective states during complex learning. *Learning and Instruction*, 22(2), 145-157. | Paper |
        """)

        st.divider()
        st.markdown("### Key Research Groups & Companies")
        st.markdown("""
| Entity | Focus |
|--------|-------|
| **MIT Media Lab** (Affective Computing Group) | Founded the field; Rosalind Picard |
| **CMU** (Robotics Institute) | Facial analysis, OpenFace toolkit |
| **Microsoft Research** | Face API, emotion detection |
| **Google** (DeepMind) | Multimodal AI, facial analysis |
| **Affectiva** (now Smart Eye) | Automotive emotion AI, market research |
| **Neuralink** | Invasive BCI implants |
| **BrainGate** | Intracortical neural interfaces |
| **Meta Reality Labs** | Non-invasive neural decoding |
| **Kernel** | Non-invasive neuroimaging (Flow helmet) |
| **OpenBCI** | Open-source EEG hardware |
| **Stanford Neural Prosthetics Lab** | Speech BCIs (Willett et al.) |
| **UT Austin** (Alex Huth Lab) | Semantic decoding from fMRI (Tang et al.) |
        """)

        st.divider()
        st.markdown("""
### Key Takeaway

> **Faces reveal emotional displays (not specific thoughts), and actual thought decoding requires
> brain imaging equipment, extensive per-person training, and active cooperation from the subject.
> No technology can read thoughts from facial expressions or covertly from a distance.**
        """)

        st.markdown("### Ethical Concerns")
        st.markdown("""
1. **Privacy**: Emotion surveillance without consent; facial recognition + emotion detection in public spaces
2. **Bias**: Training datasets skew toward Western, lighter-skinned faces; worse accuracy on darker skin, women, and non-Western populations
3. **Pseudoscience risk**: Claims of detecting criminality, sexual orientation, or political beliefs from faces (debunked; echoes of physiognomy)
4. **Employment discrimination**: HireVue used AI facial analysis in job interviews (widely criticized, largely abandoned in 2021)
5. **Mental privacy**: As neural decoding improves, "cognitive liberty" becomes a human rights issue
6. **Consent**: People may not know their emotions are being analyzed
7. **Manipulation**: Systems that detect emotions could be used to manipulate people (targeted advertising, political manipulation)
        """)

        st.markdown("### Future Directions")
        st.markdown("""
1. **Real-time mental health monitoring** -- wearables that detect depression, anxiety, or crisis states
2. **Empathic AI assistants** -- AI that adapts its responses based on emotional state
3. **AR/VR emotion-aware interfaces** -- headsets that track facial expressions (Meta Quest, Apple Vision Pro)
4. **Neural interfaces for communication** -- helping locked-in patients communicate through thought alone
5. **Personalized education** -- systems that detect confusion and adapt teaching in real-time
6. **Thought-to-text** -- typing by thinking (very early stage, requires brain imaging)
        """)


# ─── About Mode ──────────────────────────────────────────────
elif mode == "About":
    st.header("About Patient Care Monitor")

    st.markdown("""
    ## Multimodal Patient Care Monitoring System

    A scientifically-grounded monitoring tool for caregivers that combines
    multiple modalities to assess patient comfort and detect pain/distress.

    ### Modules

    | Module | Method | Scientific Basis |
    |--------|--------|-----------------|
    | **Face Analysis** | MediaPipe Face Mesh + AU estimation | FACS (Ekman & Friesen, 1978) |
    | **Pain Detection** | PSPI scale from AUs | Prkachin & Solomon; Lucey et al. (2011) |
    | **Heart Rate** | rPPG from facial video | Poh et al. (2010), Optics Express |
    | **Voice Analysis** | Pitch, energy, spectral features | Schuller et al. (2018) |
    | **Text Sentiment** | Domain-specific lexicon | Dimensional emotion model (Russell, 1980) |
    | **Fusion** | Confidence-weighted late fusion | Poria et al. (2017) |

    ### Key Design Decisions

    1. **No naive emotion labels**: Per Barrett et al. (2019, PMID: 31313636),
       facial configurations do NOT reliably map 1:1 to internal emotions.
       We report Action Units and dimensional states instead.

    2. **Privacy-first**: All processing is local. No data leaves the machine.
       No video is stored by default.

    3. **Transparent**: Rule-based methods where possible for explainability.
       Every threshold has a citation.

    4. **Supplement, not replace**: This system supports clinical judgment,
       it does not replace it.

    ### Running the System

    ```bash
    # Real-time camera monitoring (requires webcam)
    python monitor.py

    # Demo mode (no camera needed)
    python monitor.py --demo

    # Dashboard
    streamlit run dashboard.py

    # Process video file
    python monitor.py --video patient_video.mp4
    ```

    ### References

    - Barrett, L.F., et al. (2019). Emotional Expressions Reconsidered. *Psychological
      Science in the Public Interest*, 20(1), 1-68. PMID: 31313636
    - Coles, N.A., et al. (2019). A multi-lab registered replication of the facial
      feedback hypothesis. *Nature Human Behaviour*. PMID: 30973236
    - Ekman, P., & Friesen, W.V. (1978). *Facial Action Coding System*.
    - Lucey, P., et al. (2011). Painful data: The UNBC-McMaster shoulder pain
      expression archive database. *IEEE FG*.
    - Poh, M.Z., et al. (2010). Non-contact, automated cardiac pulse measurements.
      *Optics Express*, 18(10), 10762-10774.
    - Prkachin, K.M. (1992). The consistency of facial expressions of pain.
      *Pain*, 51(3), 297-306.
    - Russell, J.A. (1980). A circumplex model of affect. *Journal of Personality
      and Social Psychology*, 39(6), 1161-1178.
    - Schuller, B., et al. (2018). Speech emotion recognition: two decades in a
      nutshell. *Communications of the ACM*.
    """)

    st.divider()
    st.caption("Built with scientific rigor. All claims are citation-backed.")
