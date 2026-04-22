"""Alert engine with cooldown + consecutive-frame gating.

Designed against the well-documented problem of *alert fatigue* in clinical
monitoring (Sendelbach & Funk 2013; The Joint Commission Sentinel Event
Alert #50). An alert is only emitted when:
    (a) the trigger condition persists for N consecutive frames, AND
    (b) no alert of the same key fired within the cooldown window.

Every alert carries an explicit `reason` field stating the evidence — no
black-box alarms.
"""
from __future__ import annotations
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Deque, Dict, List, Optional

from .distress_state import DistressState
from ..features.pain import PainAssessment, PainLevel
from ..features.rppg import HeartRateResult


class AlertLevel(str, Enum):
    NORMAL = "normal"
    ATTENTION = "attention"
    CONCERN = "concern"
    URGENT = "urgent"


@dataclass
class Alert:
    key: str
    level: AlertLevel
    reason: str
    evidence: Dict[str, float] = field(default_factory=dict)
    timestamp: float = 0.0


class AlertEngine:
    def __init__(self, cooldown_s: float = 30.0, consecutive: int = 5) -> None:
        self.cooldown_s = cooldown_s
        self.consecutive = consecutive
        self._last_fired: Dict[str, float] = {}
        self._streak: Dict[str, int] = defaultdict(int)
        self._history: Deque[Alert] = deque(maxlen=200)

    def _gate(self, key: str, now: float) -> bool:
        """Increment the streak; only pass once it reaches the threshold AND
        the cooldown since last fire has elapsed."""
        self._streak[key] += 1
        if self._streak[key] < self.consecutive:
            return False
        if now - self._last_fired.get(key, 0.0) < self.cooldown_s:
            return False
        self._last_fired[key] = now
        self._streak[key] = 0
        return True

    def _reset(self, key: str) -> None:
        self._streak[key] = 0

    def evaluate(self,
                 distress: DistressState,
                 pain: PainAssessment,
                 hr: Optional[HeartRateResult]) -> List[Alert]:
        now = time.time()
        fired: List[Alert] = []

        # --- Severe pain ---
        if pain.level == PainLevel.SEVERE:
            if self._gate("severe_pain", now):
                fired.append(Alert(
                    key="severe_pain",
                    level=AlertLevel.URGENT,
                    reason=f"PSPI={pain.pspi:.1f} persisted ≥ severe threshold "
                           f"({self.consecutive} frames)",
                    evidence={"pspi": pain.pspi, "confidence": pain.confidence,
                              **pain.contributing_aus},
                    timestamp=now,
                ))
        else:
            self._reset("severe_pain")

        # --- Moderate pain ---
        if pain.level == PainLevel.MODERATE:
            if self._gate("moderate_pain", now):
                fired.append(Alert(
                    key="moderate_pain",
                    level=AlertLevel.CONCERN,
                    reason=f"PSPI={pain.pspi:.1f} sustained at moderate level",
                    evidence={"pspi": pain.pspi, "confidence": pain.confidence},
                    timestamp=now,
                ))
        else:
            self._reset("moderate_pain")

        # --- Tachycardia ---
        if hr and hr.is_abnormal and hr.abnormality == "tachycardia" and hr.confidence > 0.4:
            if self._gate("tachycardia", now):
                fired.append(Alert(
                    key="tachycardia",
                    level=AlertLevel.CONCERN,
                    reason=f"Heart rate {hr.bpm:.0f} bpm (> 100) sustained",
                    evidence={"bpm": hr.bpm, "confidence": hr.confidence, "snr": hr.snr},
                    timestamp=now,
                ))
        else:
            self._reset("tachycardia")

        # --- Bradycardia ---
        if hr and hr.is_abnormal and hr.abnormality == "bradycardia" and hr.confidence > 0.4:
            if self._gate("bradycardia", now):
                fired.append(Alert(
                    key="bradycardia",
                    level=AlertLevel.CONCERN,
                    reason=f"Heart rate {hr.bpm:.0f} bpm (< 60) sustained",
                    evidence={"bpm": hr.bpm, "confidence": hr.confidence, "snr": hr.snr},
                    timestamp=now,
                ))
        else:
            self._reset("bradycardia")

        # --- Low comfort (dimensional) ---
        if distress.comfort < 0.25 and distress.confidence > 0.5:
            if self._gate("low_comfort", now):
                fired.append(Alert(
                    key="low_comfort",
                    level=AlertLevel.ATTENTION,
                    reason=f"Comfort score {distress.comfort:.2f} sustained below 0.25",
                    evidence={"comfort": distress.comfort,
                              "arousal": distress.arousal,
                              "confidence": distress.confidence},
                    timestamp=now,
                ))
        else:
            self._reset("low_comfort")

        for a in fired:
            self._history.append(a)
        return fired

    def history(self, n: int = 50) -> List[Alert]:
        return list(self._history)[-n:]
