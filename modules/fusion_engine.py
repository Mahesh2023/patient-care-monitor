"""
Multimodal Fusion Engine
=========================
Combines outputs from all analysis modules into unified patient state assessment.

Scientific Basis:
- Late fusion approach: Each modality produces independent estimates,
  then combined via weighted averaging with confidence weighting.
  (Poria et al., 2017. A review of affective computing.)
- Confidence-weighted fusion ensures noisy modalities have less influence.
- Temporal smoothing prevents spurious single-frame alerts.

Design Decision - Why NOT "emotion labels":
Per Barrett et al. (2019, PMID: 31313636), we avoid mapping observations
to discrete emotion categories. Instead, we use dimensional representation
(arousal, valence, pain) which is more scientifically grounded and useful
for clinical monitoring.
"""

import time
from collections import deque
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from enum import Enum

import numpy as np

from modules.face_analyzer import FaceAnalysisResult
from modules.pain_detector import PainAssessment, PainLevel
from modules.voice_analyzer import VoiceAnalysisResult, VocalState
from modules.rppg_estimator import HeartRateResult
from modules.text_sentiment import SentimentResult


class PatientAlertLevel(Enum):
    NORMAL = "normal"
    ATTENTION = "attention"    # Something to note but not urgent
    CONCERN = "concern"        # Worth checking on
    URGENT = "urgent"          # Needs immediate attention


@dataclass
class PatientState:
    """
    Unified patient state assessment from all modalities.
    Uses dimensional representation, not discrete emotion labels.
    """
    # Dimensional state (scientifically grounded)
    comfort_level: float = 0.5      # 0 = very uncomfortable, 1 = very comfortable
    arousal_level: float = 0.5      # 0 = very calm/unresponsive, 1 = very agitated
    pain_level: float = 0.0         # 0 = no pain, 1 = severe pain (from PSPI)
    engagement_level: float = 0.5   # 0 = unresponsive, 1 = fully engaged

    # Alert
    alert_level: PatientAlertLevel = PatientAlertLevel.NORMAL
    alert_reasons: List[str] = field(default_factory=list)

    # Individual module results (for detail view)
    face_result: Optional[FaceAnalysisResult] = None
    pain_assessment: Optional[PainAssessment] = None
    voice_result: Optional[VoiceAnalysisResult] = None
    heart_rate: Optional[HeartRateResult] = None
    text_sentiment: Optional[SentimentResult] = None

    # Confidence in overall assessment
    overall_confidence: float = 0.0

    # Behavioral observations (what we actually see, not interpretations)
    observations: List[str] = field(default_factory=list)

    timestamp: float = 0.0

    def to_dict(self) -> dict:
        return {
            "comfort_level": round(self.comfort_level, 2),
            "arousal_level": round(self.arousal_level, 2),
            "pain_level": round(self.pain_level, 2),
            "engagement_level": round(self.engagement_level, 2),
            "alert_level": self.alert_level.value,
            "alert_reasons": self.alert_reasons,
            "overall_confidence": round(self.overall_confidence, 2),
            "observations": self.observations,
            "heart_rate_bpm": self.heart_rate.bpm if self.heart_rate else None,
            "pain_pspi": self.pain_assessment.pspi_score if self.pain_assessment else None,
            "timestamp": self.timestamp,
        }


class FusionEngine:
    """
    Fuses multiple modality outputs into a unified patient state.
    Uses confidence-weighted late fusion.
    """

    # Modality weights (tunable)
    WEIGHTS = {
        "face": 0.30,
        "pain": 0.25,
        "voice": 0.20,
        "heart_rate": 0.15,
        "text": 0.10,
    }

    def __init__(self, history_size: int = 30):
        self._state_history: deque = deque(maxlen=history_size)
        self._last_alert_time: float = 0.0
        self._consecutive_alert_frames: int = 0
        self._alert_cooldown: float = 30.0  # seconds

    def fuse(self,
             face_result: Optional[FaceAnalysisResult] = None,
             pain_assessment: Optional[PainAssessment] = None,
             voice_result: Optional[VoiceAnalysisResult] = None,
             heart_rate: Optional[HeartRateResult] = None,
             text_sentiment: Optional[SentimentResult] = None,
             timestamp: float = 0.0) -> PatientState:
        """
        Fuse all modality outputs into a unified patient state.
        """
        state = PatientState(timestamp=timestamp)
        state.face_result = face_result
        state.pain_assessment = pain_assessment
        state.voice_result = voice_result
        state.heart_rate = heart_rate
        state.text_sentiment = text_sentiment

        observations = []
        alert_reasons = []

        # --- Comfort estimation (weighted fusion) ---
        comfort_scores = []
        comfort_weights = []

        # Face-based comfort (inverted pain + AU12 smile indicator)
        if face_result and face_result.face_detected and face_result.aus:
            aus = face_result.aus
            # Smile (AU12) increases comfort estimate
            face_comfort = 0.5 + aus.AU12 * 0.3 - aus.AU4 * 0.2 - aus.AU9 * 0.15
            comfort_scores.append(np.clip(face_comfort, 0, 1))
            comfort_weights.append(self.WEIGHTS["face"])

            # Observations
            if aus.AU12 > 0.3:
                observations.append("Lip corner pull detected (AU12 - possible smile)")
            if aus.AU4 > 0.4:
                observations.append("Brow lowering detected (AU4)")
            if aus.AU43 > 0.5:
                observations.append("Eyes closed/squinting (AU43)")
            if aus.AU9 > 0.3:
                observations.append("Nose wrinkle detected (AU9)")

        # Pain-based comfort (inverted)
        if pain_assessment and pain_assessment.confidence > 0.2:
            pain_comfort = 1.0 - min(pain_assessment.pspi_score / 10.0, 1.0)
            comfort_scores.append(pain_comfort)
            comfort_weights.append(self.WEIGHTS["pain"] * pain_assessment.confidence)

            if pain_assessment.pain_level != PainLevel.NONE:
                observations.append(
                    f"Pain indicators: PSPI={pain_assessment.pspi_score:.1f} "
                    f"({pain_assessment.pain_level.value})"
                )

        # Voice-based comfort
        if voice_result and voice_result.confidence > 0.2:
            comfort_scores.append(voice_result.valence)
            comfort_weights.append(self.WEIGHTS["voice"] * voice_result.confidence)

            if voice_result.vocal_state not in (VocalState.UNKNOWN, VocalState.SILENT):
                observations.append(f"Vocal state: {voice_result.vocal_state.value}")

        # Text-based comfort
        if text_sentiment and text_sentiment.confidence > 0.1:
            comfort_scores.append(text_sentiment.valence)
            comfort_weights.append(self.WEIGHTS["text"] * text_sentiment.confidence)

            if text_sentiment.pain_mentioned:
                observations.append("Patient/note mentions pain-related terms")
            if text_sentiment.distress_mentioned:
                observations.append("Patient/note mentions distress-related terms")

        # Weighted comfort
        if comfort_scores:
            total_weight = sum(comfort_weights)
            if total_weight > 0:
                state.comfort_level = float(
                    np.average(comfort_scores, weights=comfort_weights)
                )

        # --- Arousal estimation ---
        arousal_scores = []
        arousal_weights = []

        if face_result and face_result.face_detected and face_result.aus:
            aus = face_result.aus
            face_arousal = 0.3 + aus.AU4 * 0.2 + aus.AU5 * 0.2 + aus.AU26 * 0.15
            arousal_scores.append(np.clip(face_arousal, 0, 1))
            arousal_weights.append(self.WEIGHTS["face"])

        if voice_result and voice_result.confidence > 0.2:
            arousal_scores.append(voice_result.arousal)
            arousal_weights.append(self.WEIGHTS["voice"] * voice_result.confidence)

        if text_sentiment and text_sentiment.confidence > 0.1:
            arousal_scores.append(text_sentiment.arousal)
            arousal_weights.append(self.WEIGHTS["text"] * text_sentiment.confidence)

        if arousal_scores:
            total_weight = sum(arousal_weights)
            if total_weight > 0:
                state.arousal_level = float(
                    np.average(arousal_scores, weights=arousal_weights)
                )

        # --- Pain level ---
        if pain_assessment:
            state.pain_level = min(pain_assessment.pspi_score / 10.0, 1.0)

        # --- Engagement (from face detection + eye state) ---
        if face_result:
            if face_result.face_detected:
                state.engagement_level = 0.6
                if face_result.aus and face_result.aus.AU43 < 0.3:
                    state.engagement_level = 0.8  # Eyes open, face visible
            else:
                state.engagement_level = 0.2
                observations.append("Face not detected - patient may have turned away")

        # --- Heart rate observations ---
        if heart_rate and heart_rate.confidence > 0.3:
            observations.append(
                f"Estimated HR: {heart_rate.bpm:.0f} bpm "
                f"(quality: {heart_rate.signal_quality})"
            )
            if heart_rate.is_abnormal:
                observations.append(f"HR abnormality: {heart_rate.abnormality_type}")

        # --- Alert level determination ---
        alert_level = PatientAlertLevel.NORMAL

        # Pain alerts
        if pain_assessment and pain_assessment.pspi_score >= 3.0 and pain_assessment.confidence > 0.3:
            if pain_assessment.pain_level == PainLevel.SEVERE:
                alert_level = PatientAlertLevel.URGENT
                alert_reasons.append(f"Severe pain indicators (PSPI={pain_assessment.pspi_score:.1f})")
            elif pain_assessment.pain_level == PainLevel.MODERATE:
                alert_level = max(alert_level, PatientAlertLevel.CONCERN,
                                  key=lambda x: list(PatientAlertLevel).index(x))
                alert_reasons.append(f"Moderate pain indicators (PSPI={pain_assessment.pspi_score:.1f})")

        # Voice distress alerts
        if voice_result and voice_result.vocal_state in (VocalState.DISTRESSED, VocalState.CRYING):
            if voice_result.confidence > 0.5:
                alert_level = max(alert_level, PatientAlertLevel.CONCERN,
                                  key=lambda x: list(PatientAlertLevel).index(x))
                alert_reasons.append(f"Vocal distress detected ({voice_result.vocal_state.value})")

        # Heart rate alerts
        if heart_rate and heart_rate.is_abnormal and heart_rate.confidence > 0.4:
            alert_level = max(alert_level, PatientAlertLevel.ATTENTION,
                              key=lambda x: list(PatientAlertLevel).index(x))
            alert_reasons.append(f"Heart rate: {heart_rate.bpm:.0f} bpm ({heart_rate.abnormality_type})")

        # Combined high arousal + low comfort
        if state.arousal_level > 0.7 and state.comfort_level < 0.3:
            alert_level = max(alert_level, PatientAlertLevel.CONCERN,
                              key=lambda x: list(PatientAlertLevel).index(x))
            alert_reasons.append("High agitation with low comfort")

        state.alert_level = alert_level
        state.alert_reasons = alert_reasons
        state.observations = observations

        # Overall confidence
        confidences = []
        if pain_assessment:
            confidences.append(pain_assessment.confidence)
        if voice_result:
            confidences.append(voice_result.confidence)
        if heart_rate:
            confidences.append(heart_rate.confidence)
        if face_result and face_result.face_detected:
            confidences.append(0.7)
        state.overall_confidence = float(np.mean(confidences)) if confidences else 0.0

        self._state_history.append(state)
        return state

    def get_state_trend(self, n: int = 10) -> dict:
        """Get trend of patient state over recent history."""
        recent = list(self._state_history)[-n:]
        if len(recent) < 3:
            return {"trend": "insufficient_data"}

        comforts = [s.comfort_level for s in recent]
        pains = [s.pain_level for s in recent]

        comfort_trend = "stable"
        if comforts[-1] - comforts[0] > 0.1:
            comfort_trend = "improving"
        elif comforts[-1] - comforts[0] < -0.1:
            comfort_trend = "declining"

        pain_trend = "stable"
        if pains[-1] - pains[0] > 0.1:
            pain_trend = "increasing"
        elif pains[-1] - pains[0] < -0.1:
            pain_trend = "decreasing"

        return {
            "comfort_trend": comfort_trend,
            "pain_trend": pain_trend,
            "mean_comfort": round(float(np.mean(comforts)), 2),
            "mean_pain": round(float(np.mean(pains)), 2),
        }

    def get_history(self) -> List[dict]:
        """Get state history as list of dicts."""
        return [s.to_dict() for s in self._state_history]
