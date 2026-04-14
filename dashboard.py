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
from datetime import datetime
from pathlib import Path

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np

try:
    import streamlit as st
except ImportError:
    print("Streamlit not installed. Install with: pip install streamlit")
    print("Then run: streamlit run dashboard.py")
    sys.exit(1)

from config import DISCLAIMERS, SystemConfig
from modules.text_sentiment import TextSentimentAnalyzer
from modules.pain_detector import PainLevel
from modules.fusion_engine import PatientAlertLevel
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


# ─── Sidebar ─────────────────────────────────────────────────
with st.sidebar:
    st.title("Patient Care Monitor")
    st.caption("Multimodal patient monitoring for caregivers")

    st.divider()

    # Mode selector
    mode = st.radio("Mode", ["Dashboard", "Session Review", "Text Analysis", "About"])

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
        'This dashboard displays behavioral observations and physiological indicators. '
        'All readings should supplement, not replace, professional clinical assessment. '
        'See Scientific Disclaimers in the sidebar.'
        '</div>',
        unsafe_allow_html=True,
    )

    # Generate demo data for display
    if st.button("Generate Demo Data", type="primary"):
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

        # Current state (latest)
        current = states[-1]

        # Top metrics row
        col1, col2, col3, col4, col5 = st.columns(5)
        with col1:
            comfort_pct = int(current["comfort_level"] * 100)
            st.metric("Comfort Level", f"{comfort_pct}%",
                       delta=f"{(current['comfort_level'] - states[-2]['comfort_level'])*100:+.0f}%" if len(states) > 1 else None)
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

        # Alert check
        if current["pain_level"] > 4:
            st.markdown(
                f'<div class="alert-concern">CONCERN: Pain indicators elevated '
                f'(PSPI={current["pain_level"]:.1f}). Consider checking on patient.</div>',
                unsafe_allow_html=True,
            )

        # Charts
        st.subheader("Trends Over Time")
        col_left, col_right = st.columns(2)

        with col_left:
            # Pain & Comfort over time
            import pandas as pd
            df = pd.DataFrame(states)
            chart_data = df[["timestamp", "pain_level", "comfort_level"]].rename(
                columns={"pain_level": "Pain (PSPI/10)", "comfort_level": "Comfort"}
            )
            chart_data["Pain (PSPI/10)"] = chart_data["Pain (PSPI/10)"] / 10.0
            st.line_chart(chart_data.set_index("timestamp"), use_container_width=True)
            st.caption("Pain (PSPI scale, /10) and Comfort (0-1) over time")

        with col_right:
            # Heart rate
            hr_data = df[["timestamp", "heart_rate"]].rename(
                columns={"heart_rate": "Heart Rate (bpm)"}
            )
            st.line_chart(hr_data.set_index("timestamp"), use_container_width=True)
            st.caption("Estimated heart rate (rPPG) - for monitoring trends only")

        # Observations panel
        st.subheader("Recent Observations")
        current_scenario = current["scenario"]
        obs_text = {
            "Resting": [
                "Face detected, eyes open",
                "Patient appears restful",
                "Vital signs within normal range",
            ],
            "Mild discomfort": [
                "Brow lowering detected (AU4)",
                "Slight increase in arousal indicators",
                "Heart rate slightly elevated",
            ],
            "Pain episode": [
                "Brow lowering detected (AU4)",
                "Nose wrinkle detected (AU9)",
                "Eyes squinting (AU43)",
                "Pain PSPI score elevated",
                "Heart rate above resting baseline",
            ],
            "Recovery": [
                "Pain indicators decreasing",
                "Comfort level improving",
                "Heart rate returning to baseline",
            ],
            "Comfortable": [
                "Lip corner pull detected (AU12 - possible smile)",
                "Patient appears comfortable",
                "Vital signs within normal range",
            ],
        }
        for obs in obs_text.get(current_scenario, ["Monitoring..."]):
            st.info(obs)

    else:
        st.info("Click 'Generate Demo Data' to see the dashboard in action, "
                "or run `python monitor.py` for real-time camera monitoring.")


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
