"""Prkachin & Solomon Pain Intensity (PSPI) — clinical pain score from AUs.

Canonical formula (Prkachin 1992; Prkachin & Solomon 2008):
    PSPI = AU4 + max(AU6, AU7) + max(AU9, AU10) + AU43

where each AU is graded on the A-E 0-5 FACS intensity scale, yielding a
[0, 16] range. Validated in the UNBC-McMaster Shoulder Pain Archive
(Lucey et al. 2011) for non-verbal pain detection.

We scale MediaPipe-derived AUs (each on [0, 1]) by 5 to approximate the
FACS A-E intensity, then compute PSPI on the original [0, 16] scale.
Temporal smoothing and a confidence estimator (inverse of local std) are
applied to mitigate single-frame noise.
"""
from __future__ import annotations
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Deque, Dict, List, Optional

import numpy as np


class PainLevel(str, Enum):
    NONE = "none"
    MILD = "mild"
    MODERATE = "moderate"
    SEVERE = "severe"


@dataclass
class PainAssessment:
    pspi: float = 0.0
    pspi_raw: float = 0.0
    level: PainLevel = PainLevel.NONE
    confidence: float = 0.0
    contributing_aus: Dict[str, float] = field(default_factory=dict)
    trend: str = "stable"        # increasing, decreasing, stable, insufficient_data
    timestamp: float = 0.0


class PSPIDetector:
    def __init__(self,
                 mild: float = 1.5,
                 moderate: float = 4.0,
                 severe: float = 8.0,
                 window: int = 15) -> None:
        self.mild = mild
        self.moderate = moderate
        self.severe = severe
        self.window = window
        self._history: Deque[float] = deque(maxlen=window)

    def compute(self, aus: Dict[str, float]) -> float:
        """Raw PSPI on the [0, 16] scale."""
        def s(au: str) -> float:
            return float(aus.get(au, 0.0)) * 5.0  # [0,1] -> [0,5] FACS-like
        pspi = s("AU4") + max(s("AU6"), s("AU7")) + max(s("AU9"), s("AU10")) + s("AU43")
        return float(min(16.0, max(0.0, pspi)))

    def _classify(self, pspi: float) -> PainLevel:
        if pspi >= self.severe:
            return PainLevel.SEVERE
        if pspi >= self.moderate:
            return PainLevel.MODERATE
        if pspi >= self.mild:
            return PainLevel.MILD
        return PainLevel.NONE

    def _trend(self) -> str:
        if len(self._history) < 6:
            return "insufficient_data"
        recent = float(np.mean(list(self._history)[-3:]))
        older = float(np.mean(list(self._history)[-6:-3]))
        d = recent - older
        if d > 0.5:
            return "increasing"
        if d < -0.5:
            return "decreasing"
        return "stable"

    def assess(self, aus: Dict[str, float], timestamp: float = 0.0) -> PainAssessment:
        raw = self.compute(aus)
        self._history.append(raw)
        if len(self._history) >= 3:
            weights = np.linspace(0.5, 1.0, len(self._history))
            smoothed = float(np.average(list(self._history), weights=weights))
        else:
            smoothed = raw
        if len(self._history) >= 5:
            std = float(np.std(list(self._history)[-5:]))
            conf = float(max(0.0, 1.0 - std / 5.0))
        else:
            conf = 0.3
        return PainAssessment(
            pspi=round(smoothed, 3),
            pspi_raw=round(raw, 3),
            level=self._classify(smoothed),
            confidence=round(conf, 3),
            contributing_aus={k: round(float(aus.get(k, 0.0)), 3)
                              for k in ("AU4", "AU6", "AU7", "AU9", "AU10", "AU43")},
            trend=self._trend(),
            timestamp=timestamp,
        )

    def reset(self) -> None:
        self._history.clear()
