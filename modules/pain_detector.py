"""
Pain Detector Module
====================
Computes pain scores from Action Unit estimates.

Scientific Basis:
- Prkachin & Solomon Pain Intensity (PSPI) scale:
    PSPI = AU4 + max(AU6, AU7) + max(AU9, AU10) + AU43
    Range: 0-16

- Validated in: Lucey et al. (2011). Painful data: The UNBC-McMaster
  shoulder pain expression archive database. IEEE FG.

- The PSPI has been shown effective for automated pain detection in
  non-verbal patients (Ashraf et al., 2009; Werner et al., 2017).

Limitations:
- AU estimation from landmarks is less precise than EMG-based FACS coding
- Pain expression varies across individuals and cultures
- Some patients may suppress pain displays (stoicism bias)
- Must be used as supplement to, not replacement for, clinical assessment
"""

import logging
from dataclasses import dataclass
from typing import List, Optional
from enum import Enum

import numpy as np

from modules.face_analyzer import AUEstimates

logger = logging.getLogger(__name__)


class PainLevel(Enum):
    NONE = "none"
    MILD = "mild"
    MODERATE = "moderate"
    SEVERE = "severe"


@dataclass
class PainAssessment:
    """Pain assessment result."""
    pspi_score: float = 0.0
    pain_level: PainLevel = PainLevel.NONE
    contributing_aus: dict = None  # Which AUs contributed
    confidence: float = 0.0       # Confidence in the estimate
    timestamp: float = 0.0

    def __post_init__(self):
        if self.contributing_aus is None:
            self.contributing_aus = {}


class PainDetector:
    """
    Detects pain from Action Unit estimates using the PSPI scale.
    Maintains a temporal window for smoothing and confidence estimation.
    """

    def __init__(self, mild_threshold: float = 1.5, moderate_threshold: float = 4.0,
                 severe_threshold: float = 8.0, window_size: int = 15):
        self.mild_threshold = mild_threshold
        self.moderate_threshold = moderate_threshold
        self.severe_threshold = severe_threshold
        self.window_size = window_size
        self._score_history: List[float] = []

    def compute_pspi(self, aus: AUEstimates) -> float:
        """
        Compute Prkachin & Solomon Pain Intensity score.
        PSPI = AU4 + max(AU6, AU7) + max(AU9, AU10) + AU43

        Each AU is on a 0-1 scale here, so we scale to approximate
        the 0-5 FACS intensity scale (A-E) by multiplying by 5.
        """
        # Scale AU estimates (0-1) to FACS-like intensity (0-5)
        au4 = aus.AU4 * 5.0
        au6 = aus.AU6 * 5.0
        au7 = aus.AU7 * 5.0
        au9 = aus.AU9 * 5.0
        au10 = aus.AU10 * 5.0
        au43 = aus.AU43 * 5.0

        pspi = au4 + max(au6, au7) + max(au9, au10) + au43
        return min(pspi, 16.0)  # Clamp to max PSPI

    def classify_pain(self, pspi_score: float) -> PainLevel:
        """Classify pain level from PSPI score."""
        if pspi_score >= self.severe_threshold:
            return PainLevel.SEVERE
        elif pspi_score >= self.moderate_threshold:
            return PainLevel.MODERATE
        elif pspi_score >= self.mild_threshold:
            return PainLevel.MILD
        return PainLevel.NONE

    def assess(self, aus: Optional[AUEstimates], timestamp: float = 0.0) -> PainAssessment:
        """
        Perform pain assessment from Action Unit estimates.
        Uses temporal smoothing over a sliding window.
        """
        try:
            if aus is None:
                return PainAssessment(timestamp=timestamp)

            raw_pspi = self.compute_pspi(aus)
            self._score_history.append(raw_pspi)

            # Keep window size bounded
            if len(self._score_history) > self.window_size:
                self._score_history = self._score_history[-self.window_size:]

            # Temporal smoothing: weighted average favoring recent frames
            if len(self._score_history) >= 3:
                weights = np.linspace(0.5, 1.0, len(self._score_history))
                smoothed_pspi = float(np.average(self._score_history, weights=weights))
            else:
                smoothed_pspi = raw_pspi

            # Confidence based on score consistency
            if len(self._score_history) >= 5:
                std = np.std(self._score_history[-5:])
                confidence = max(0.0, 1.0 - std / 5.0)  # Lower std = higher confidence
            else:
                confidence = 0.3  # Low confidence with few frames

            pain_level = self.classify_pain(smoothed_pspi)

            contributing = {
                "AU4_brow_lower": round(aus.AU4, 3),
                "AU6_cheek_raise": round(aus.AU6, 3),
                "AU7_lid_tighten": round(aus.AU7, 3),
                "AU9_nose_wrinkle": round(aus.AU9, 3),
                "AU10_lip_raise": round(aus.AU10, 3),
                "AU43_eyes_closed": round(aus.AU43, 3),
            }

            return PainAssessment(
                pspi_score=round(smoothed_pspi, 2),
                pain_level=pain_level,
                contributing_aus=contributing,
                confidence=round(confidence, 2),
                timestamp=timestamp,
            )
        except Exception as e:
            logger.error(f"Error in pain assessment: {e}")
            return PainAssessment(timestamp=timestamp)

    def get_trend(self) -> str:
        """Get pain trend over recent window."""
        try:
            if len(self._score_history) < 5:
                return "insufficient_data"
            recent = np.mean(self._score_history[-3:])
            older = np.mean(self._score_history[-6:-3])
            diff = recent - older
            if diff > 0.5:
                return "increasing"
            elif diff < -0.5:
                return "decreasing"
            return "stable"
        except Exception as e:
            logger.error(f"Error computing pain trend: {e}")
            return "error"

    def reset(self):
        self._score_history.clear()
