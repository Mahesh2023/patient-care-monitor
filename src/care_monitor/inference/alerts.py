"""Smart alert engine: persistence + cooldown + corroboration + quality gating.

Designed against *alarm fatigue* (Sendelbach & Funk 2013; Joint Commission
NPSG.06.01.01; AAMI alarm-management guidance):
  (a) persistence: condition must hold for N consecutive samples;
  (b) cooldown: no repeat of the same alert key within the window;
  (c) multi-parameter corroboration ("smart alarms"): a facial pain alert is
      raised one priority level higher when an independent channel agrees
      (vocal distress, rPPG tachycardia, abnormal respiration). Single-channel
      evidence is still reported — never suppressed — at the lower level;
  (d) signal-quality gating: facial alerts are withheld while capture quality
      is poor or the per-patient baseline is still calibrating; vital-sign
      alerts require a passing signal-quality index;
  (e) per-patient thresholds and muted keys (AACN: customise alarm parameters
      to the individual patient).

Every alert carries an explicit `reason` stating the evidence.
"""
from __future__ import annotations

import time
from collections import defaultdict, deque
from dataclasses import asdict, dataclass, field, fields
from enum import Enum
from typing import Any, Optional

from ..config import settings
from ..features.pain import PainAssessment, PainLevel
from ..features.respiration import RespirationResult
from ..features.rppg import HeartRateResult
from .distress_state import DistressState

ALERT_KEYS = ("severe_pain", "moderate_pain", "tachycardia", "bradycardia",
              "tachypnea", "bradypnea", "vocal_distress", "low_comfort")


class AlertLevel(str, Enum):
    NORMAL = "normal"
    ATTENTION = "attention"
    CONCERN = "concern"
    URGENT = "urgent"


_UP = {AlertLevel.ATTENTION: AlertLevel.CONCERN, AlertLevel.CONCERN: AlertLevel.URGENT,
       AlertLevel.URGENT: AlertLevel.URGENT}


@dataclass
class AlertSettings:
    """Per-patient alarm configuration (defaults from global settings)."""
    pspi_moderate: float = field(default_factory=lambda: settings.pspi_moderate_threshold)
    pspi_severe: float = field(default_factory=lambda: settings.pspi_severe_threshold)
    hr_high: float = 100.0
    hr_low: float = 60.0
    rr_high: float = 24.0
    rr_low: float = 10.0
    cooldown_s: float = field(default_factory=lambda: settings.alert_cooldown_seconds)
    consecutive: int = field(default_factory=lambda: settings.alert_consecutive_frames)
    muted: tuple[str, ...] = ()

    @classmethod
    def from_dict(cls, d: Optional[dict[str, Any]]) -> AlertSettings:
        s = cls()
        if d:
            names = {f.name for f in fields(cls)}
            for k, v in d.items():
                if k in names and v is not None:
                    setattr(s, k, tuple(v) if k == "muted" else type(getattr(s, k))(v))
        return s

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["muted"] = list(self.muted)
        return d


@dataclass
class Alert:
    key: str
    level: AlertLevel
    reason: str
    evidence: dict[str, float] = field(default_factory=dict)
    timestamp: float = 0.0


class AlertEngine:
    def __init__(self, cooldown_s: float = 30.0, consecutive: int = 5,
                 config: Optional[AlertSettings] = None) -> None:
        self.config = config or AlertSettings(cooldown_s=cooldown_s, consecutive=consecutive)
        self._last_fired: dict[str, float] = {}
        self._streak: dict[str, int] = defaultdict(int)
        self._history: deque[Alert] = deque(maxlen=200)

    @property
    def cooldown_s(self) -> float:
        return self.config.cooldown_s

    @property
    def consecutive(self) -> int:
        return self.config.consecutive

    def _gate(self, key: str, now: float) -> bool:
        """Increment the streak; pass once it reaches the threshold AND cooldown elapsed."""
        if key in self.config.muted:
            return False
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

    def _check(self, key: str, cond: bool, now: float) -> bool:
        if cond:
            return self._gate(key, now)
        self._reset(key)
        return False

    def evaluate(self,
                 distress: DistressState,
                 pain: PainAssessment,
                 hr: Optional[HeartRateResult],
                 now: Optional[float] = None,
                 *,
                 resp: Optional[RespirationResult] = None,
                 vocal_distress: bool = False,
                 quality_ok: bool = True,
                 calibrating: bool = False) -> list[Alert]:
        now = time.time() if now is None else now
        fired: list[Alert] = []
        facial_ok = quality_ok and not calibrating

        hr_ok = bool(hr and hr.signal_quality == "good" and hr.confidence > 0.4)
        rr_ok = bool(resp and resp.signal_quality == "good")
        corroborators = []
        if vocal_distress:
            corroborators.append("vocal distress")
        if hr_ok and hr.abnormality == "tachycardia":
            corroborators.append(f"HR {hr.bpm:.0f} bpm")
        if rr_ok and resp.is_abnormal:
            corroborators.append(f"RR {resp.brpm:.0f}/min")
        corr = f"; corroborated by {', '.join(corroborators)}" if corroborators else "; facial evidence only — please verify"

        def fire(key: str, base: AlertLevel, reason: str, evidence: dict[str, float], boost: bool = False) -> None:
            level = _UP[base] if boost and corroborators else base
            fired.append(Alert(key, level, reason, evidence, now))

        if self._check("severe_pain", facial_ok and pain.level == PainLevel.SEVERE, now):
            fire("severe_pain", AlertLevel.CONCERN,
                 f"PSPI={pain.pspi:.1f} sustained ≥ severe threshold ({self.consecutive} samples){corr}",
                 {"pspi": pain.pspi, "confidence": pain.confidence, **pain.contributing_aus}, boost=True)
        if self._check("moderate_pain", facial_ok and pain.level == PainLevel.MODERATE, now):
            fire("moderate_pain", AlertLevel.ATTENTION,
                 f"PSPI={pain.pspi:.1f} sustained at moderate level{corr}",
                 {"pspi": pain.pspi, "confidence": pain.confidence}, boost=True)
        for key, cmp in (("tachycardia", ">"), ("bradycardia", "<")):
            if self._check(key, hr_ok and hr.abnormality == key, now):
                lim = self.config.hr_high if key == "tachycardia" else self.config.hr_low
                fire(key, AlertLevel.CONCERN, f"Heart rate {hr.bpm:.0f} bpm ({cmp} {lim:.0f}) sustained, rPPG SNR {hr.snr:.1f} dB",
                     {"bpm": hr.bpm, "confidence": hr.confidence, "snr_db": hr.snr})
        for key, cmp in (("tachypnea", ">"), ("bradypnea", "<")):
            if self._check(key, rr_ok and resp.abnormality == key, now):
                lim = self.config.rr_high if key == "tachypnea" else self.config.rr_low
                fire(key, AlertLevel.CONCERN, f"Respiratory rate {resp.brpm:.0f}/min ({cmp} {lim:.0f}) sustained ({resp.source})",
                     {"brpm": resp.brpm, "confidence": resp.confidence})
        if self._check("vocal_distress", vocal_distress, now):
            fire("vocal_distress", AlertLevel.ATTENTION, "Sustained distressed / crying / moaning vocal prosody",
                 {"arousal": distress.arousal})
        if self._check("low_comfort", facial_ok and distress.comfort < 0.25 and distress.confidence > 0.5, now):
            fire("low_comfort", AlertLevel.ATTENTION, f"Comfort score {distress.comfort:.2f} sustained below 0.25",
                 {"comfort": distress.comfort, "arousal": distress.arousal, "confidence": distress.confidence})

        self._history.extend(fired)
        return fired

    def history(self, n: int = 50) -> list[Alert]:
        return list(self._history)[-n:]
