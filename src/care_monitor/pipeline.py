"""SessionPipeline — numeric features in, clinical analysis out.

Replaces the v2 `CareMonitorAgent`. Face perception (MediaPipe) now runs in
the *browser*; the client streams compact per-frame numeric samples:

    {"t": <epoch ms>,
     "bs":  [float]*len(BLENDSHAPE_NAMES) | null,   # null => no face
     "m":   [float]*16 | null,                      # column-major transform
     "lm":  [float]*2*len(GAZE_LANDMARKS) | null,   # x,y pairs (normalised)
     "rgb": [r, g, b] | null}                       # forehead ROI mean

plus optional per-batch `audio` (voice prosody features) and `text`
(caregiver note). All per-session state is bounded in size, so memory per
stream is a few tens of KB regardless of session length.

Thread-unsafe by design: exactly one pipeline per live stream.
"""
from __future__ import annotations

import math
import time
from collections import deque
from dataclasses import asdict, dataclass, field
from typing import Any, Optional
from collections.abc import Mapping, Sequence

from .config import settings
from .features.action_units import (
    BLENDSHAPE_NAMES, TemporalSmoother, action_units_from_vector, active_aus,
)
from .features.blink import BlinkTracker
from .features.micro_expressions import MicroExpressionDetector
from .features.pain import PainAssessment, PSPIDetector
from .features.rppg import HeartRateResult, RPPGEstimator
from .features.text_sentiment import TextSentimentAnalyzer
from .features.voice import VoiceFeatures, classify as classify_voice
from .inference.alerts import AlertEngine
from .inference.distress_state import infer_distress
from .perception.head_pose import head_pose_from_column_major
from .perception.iris_gaze import GAZE_LANDMARKS, SparseLandmarks, estimate_gaze

PROTOCOL_VERSION = 1
VOICE_TTL_S = 3.0
TEXT_TTL_S = 60.0
_N_BS = len(BLENDSHAPE_NAMES)
_N_LM = 2 * len(GAZE_LANDMARKS)


class ProtocolError(ValueError):
    pass


def _floats(seq: Any, n: int, lo: float = -1e6, hi: float = 1e6) -> Optional[list[float]]:
    if seq is None:
        return None
    if not isinstance(seq, (list, tuple)) or len(seq) != n:
        raise ProtocolError(f"expected list of {n} numbers")
    out = []
    for v in seq:
        if not isinstance(v, (int, float)) or isinstance(v, bool):
            raise ProtocolError("non-numeric value")
        f = float(v)
        out.append(min(hi, max(lo, f)) if math.isfinite(f) else 0.0)
    return out


@dataclass
class Sample:
    t: float                      # seconds
    bs: Optional[list[float]]
    m: Optional[list[float]]
    lm: Optional[list[float]]
    rgb: Optional[list[float]]

    @classmethod
    def parse(cls, raw: Mapping[str, Any]) -> Sample:
        if not isinstance(raw, Mapping):
            raise ProtocolError("sample must be an object")
        t = raw.get("t")
        if not isinstance(t, (int, float)) or not math.isfinite(t):
            raise ProtocolError("sample.t must be a number (epoch ms)")
        return cls(
            t=float(t) / 1000.0,
            bs=_floats(raw.get("bs"), _N_BS, 0.0, 1.0),
            m=_floats(raw.get("m"), 16),
            lm=_floats(raw.get("lm"), _N_LM, -2.0, 3.0),
            rgb=_floats(raw.get("rgb"), 3, 0.0, 255.0),
        )


@dataclass
class BatchResult:
    ts: float
    face_detected: bool = False
    action_units: dict[str, float] = field(default_factory=dict)
    active_aus: list[str] = field(default_factory=list)
    head_pose: dict[str, float] = field(default_factory=dict)
    gaze: dict[str, Any] = field(default_factory=dict)
    blink_rpm: float = 0.0
    micro_events: list[dict[str, Any]] = field(default_factory=list)
    pain: dict[str, Any] = field(default_factory=dict)
    heart_rate: dict[str, Any] = field(default_factory=dict)
    voice: dict[str, Any] = field(default_factory=dict)
    text: dict[str, Any] = field(default_factory=dict)
    distress: dict[str, Any] = field(default_factory=dict)
    alerts: list[dict[str, Any]] = field(default_factory=list)
    samples: int = 0
    samples_per_s: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class _Rollup:
    """Per-interval aggregates persisted to `session_metrics`."""

    def __init__(self, start: float) -> None:
        self.start = start
        self.n = 0
        self.face_n = 0
        self.pspi_sum = self.pspi_max = 0.0
        self.comfort_sum = self.arousal_sum = 0.0
        self.hr_sum = 0.0
        self.hr_n = 0
        self.alerts = 0

    def add(self, pain: Optional[PainAssessment], comfort: float, arousal: float) -> None:
        self.n += 1
        if pain is not None:
            self.face_n += 1
            self.pspi_sum += pain.pspi
            self.pspi_max = max(self.pspi_max, pain.pspi)
            self.comfort_sum += comfort
            self.arousal_sum += arousal

    def to_row(self) -> dict[str, Any]:
        d = max(1, self.face_n)
        return {
            "bucket_start": self.start,
            "samples": self.n,
            "face_samples": self.face_n,
            "avg_pspi": round(self.pspi_sum / d, 3),
            "max_pspi": round(self.pspi_max, 3),
            "avg_comfort": round(self.comfort_sum / d, 3) if self.face_n else None,
            "avg_arousal": round(self.arousal_sum / d, 3) if self.face_n else None,
            "avg_hr": round(self.hr_sum / self.hr_n, 1) if self.hr_n else None,
            "alerts": self.alerts,
        }


class SessionPipeline:
    def __init__(self, session_id: str = "default") -> None:
        self.session_id = session_id
        self.au_smoother = TemporalSmoother(alpha=0.35, window_size=5)
        self.blink = BlinkTracker()
        self.micro = MicroExpressionDetector(frame_ms=1000.0 / settings.target_fps)
        self.pain = PSPIDetector(
            mild=settings.pspi_mild_threshold,
            moderate=settings.pspi_moderate_threshold,
            severe=settings.pspi_severe_threshold,
        )
        self.rppg = RPPGEstimator(
            resample_hz=settings.rppg_resample_hz,
            window_s=settings.rppg_window_seconds,
            low_hz=settings.rppg_bandpass_low_hz,
            high_hz=settings.rppg_bandpass_high_hz,
        )
        self.text = TextSentimentAnalyzer()
        self.alerts = AlertEngine(
            cooldown_s=settings.alert_cooldown_seconds,
            consecutive=settings.alert_consecutive_frames,
        )
        self.started_at = time.time()
        self.sample_count = 0
        self._last_t: float = 0.0
        self._rate_window: deque[float] = deque(maxlen=64)
        self._micro_history: deque[str] = deque(maxlen=20)
        self._voice: Optional[dict[str, Any]] = None
        self._voice_t = 0.0
        self._text: Optional[dict[str, Any]] = None
        self._text_t = 0.0
        self._last_llm = 0.0
        self._last_hr: Optional[HeartRateResult] = None
        self._rollup = _Rollup(self.started_at)
        self.last_snapshot: dict[str, Any] = {}

    # ------------------------------------------------------------------
    def _ingest_voice(self, audio: Any, now: float) -> None:
        if isinstance(audio, Mapping):
            self._voice = classify_voice(VoiceFeatures.from_mapping(audio)).to_dict()
            self._voice_t = now

    def _ingest_text(self, text: Any, now: float) -> None:
        if isinstance(text, str) and text.strip():
            r = self.text.analyze(text, now)
            self._text = {
                "valence": r.valence, "arousal": r.arousal,
                "pain_mentioned": r.pain_mentioned,
                "distress_mentioned": r.distress_mentioned,
                "key_terms": r.key_terms[:20], "confidence": r.confidence,
            }
            self._text_t = now

    def process_batch(self, msg: Mapping[str, Any], now: Optional[float] = None) -> BatchResult:
        """Process one client batch. Raises ProtocolError on malformed input."""
        now = time.time() if now is None else now
        raw_samples = msg.get("samples") or []
        if not isinstance(raw_samples, list):
            raise ProtocolError("samples must be a list")
        if len(raw_samples) > settings.max_samples_per_batch:
            raise ProtocolError("too many samples in batch")
        samples = sorted((Sample.parse(s) for s in raw_samples), key=lambda s: s.t)

        self._ingest_voice(msg.get("audio"), now)
        self._ingest_text(msg.get("text"), now)
        voice = self._voice if self._voice and now - self._voice_t < VOICE_TTL_S else None
        text = self._text if self._text and now - self._text_t < TEXT_TTL_S else None

        result = BatchResult(ts=now, samples=len(samples))
        if voice:
            result.voice = voice
        if text:
            result.text = text

        aus: dict[str, float] = {}
        pain_a: Optional[PainAssessment] = None
        distress = None
        for s in samples:
            if s.t <= self._last_t:
                continue  # replay / out-of-order
            self._last_t = s.t
            self._rate_window.append(s.t)
            self.sample_count += 1
            if s.bs is None:
                self._rollup.add(None, 0.0, 0.0)
                continue
            result.face_detected = True
            aus = self.au_smoother.update(action_units_from_vector(s.bs))
            if s.m is not None:
                result.head_pose = {k: round(v, 2) for k, v in head_pose_from_column_major(s.m).items()}
            if s.lm is not None:
                g = estimate_gaze(SparseLandmarks(s.lm))
                result.gaze = {"h_ratio": round(g["h_ratio"], 3), "v_ratio": round(g["v_ratio"], 3),
                               "averted": g["averted"]}
            self.blink.update(aus.get("AU45", 0.0), now=s.t)
            for e in self.micro.add_frame(aus, now=s.t):
                ev = {"au": e.au, "peak": round(e.peak_intensity, 3), "duration_ms": round(e.duration_ms)}
                result.micro_events.append(ev)
                self._micro_history.append(f"{e.au}({e.duration_ms:.0f}ms)")
            if s.rgb is not None:
                self.rppg.add_sample(s.rgb, s.t)
            pain_a = self.pain.assess(aus, timestamp=s.t)
            blink_rpm = self.blink.rate_per_minute(now=s.t)
            hr_bpm = self._last_hr.bpm if self._last_hr and self._last_hr.confidence > 0.3 else 0.0
            distress = infer_distress(aus=aus, head_pose=result.head_pose, gaze=result.gaze,
                                      blink_rpm=blink_rpm, pain=pain_a,
                                      heart_rate_bpm=hr_bpm, timestamp=s.t)
            self._fuse(distress, voice, text)
            for a in self.alerts.evaluate(distress, pain_a, self._last_hr, now=now):
                result.alerts.append({"key": a.key, "level": a.level.value, "reason": a.reason,
                                      "evidence": a.evidence, "ts": a.timestamp})
                self._rollup.alerts += 1
            self._rollup.add(pain_a, distress.comfort, distress.arousal)

        # rPPG once per batch (FFT over a 20 s window — cheap, but not per sample).
        hr = self.rppg.estimate(timestamp=now)
        if hr.signal_quality != "no_signal":
            self._last_hr = hr
            result.heart_rate = {
                "bpm": hr.bpm, "confidence": hr.confidence, "snr": hr.snr,
                "quality": hr.signal_quality, "is_abnormal": hr.is_abnormal,
                "abnormality": hr.abnormality,
            }
            if hr.confidence > 0.3:
                self._rollup.hr_sum += hr.bpm
                self._rollup.hr_n += 1

        if result.face_detected and pain_a is not None and distress is not None:
            result.action_units = {k: round(v, 3) for k, v in aus.items()}
            result.active_aus = sorted(active_aus(aus))
            result.blink_rpm = round(self.blink.rate_per_minute(now=self._last_t), 1)
            result.pain = {
                "pspi": pain_a.pspi, "pspi_raw": pain_a.pspi_raw, "level": pain_a.level.value,
                "confidence": pain_a.confidence, "trend": pain_a.trend,
                "contributing_aus": pain_a.contributing_aus,
            }
            result.distress = {
                "comfort": distress.comfort, "arousal": distress.arousal, "pain": distress.pain,
                "engagement": distress.engagement, "tag": distress.behavioural_tag,
                "confidence": distress.confidence, "observations": distress.observations,
            }
            self.last_snapshot = {
                "aus": aus, "head_pose": result.head_pose, "gaze": result.gaze,
                "blink_rpm": result.blink_rpm, "pspi": pain_a.pspi, "pain_level": pain_a.level.value,
                "hr_bpm": self._last_hr.bpm if self._last_hr else 0.0,
                "hr_quality": self._last_hr.signal_quality if self._last_hr else "no_signal",
                "tag": distress.behavioural_tag, "observations": distress.observations,
                "micro_events": list(self._micro_history),
                "voice_state": voice.get("vocal_state") if voice else None,
                "text_pain": text.get("pain_mentioned") if text else None,
                "text_distress": text.get("distress_mentioned") if text else None,
            }

        if len(self._rate_window) >= 2:
            span = self._rate_window[-1] - self._rate_window[0]
            result.samples_per_s = round((len(self._rate_window) - 1) / span, 2) if span > 0 else 0.0
        return result

    @staticmethod
    def _fuse(distress, voice: Optional[dict[str, Any]], text: Optional[dict[str, Any]]) -> None:
        """Late fusion of voice / note sentiment into the facial distress state."""
        if voice and voice.get("vocal_state") not in (None, "silent", "unknown"):
            distress.arousal = (distress.arousal + voice["arousal"]) / 2.0
            distress.comfort = (distress.comfort + voice["valence"]) / 2.0
            if voice["vocal_state"] in ("distressed", "crying", "moaning"):
                distress.observations.append(f"vocal_{voice['vocal_state']}")
        if text:
            distress.arousal = (distress.arousal + text["arousal"]) / 2.0
            distress.comfort = (distress.comfort + text["valence"]) / 2.0
            if text["pain_mentioned"]:
                distress.observations.append("note_mentions_pain")
            if text["distress_mentioned"]:
                distress.observations.append("note_mentions_distress")
        distress.comfort = round(max(0.0, min(1.0, distress.comfort)), 3)
        distress.arousal = round(max(0.0, min(1.0, distress.arousal)), 3)

    # ------------------------------------------------------------------
    def llm_due(self, now: Optional[float] = None) -> bool:
        now = time.time() if now is None else now
        if not self.last_snapshot or now - self._last_llm < settings.llm_cooldown_seconds:
            return False
        self._last_llm = now
        return True

    def pop_rollup(self, now: Optional[float] = None, force: bool = False) -> Optional[dict[str, Any]]:
        now = time.time() if now is None else now
        if not force and now - self._rollup.start < settings.rollup_interval_seconds:
            return None
        row = self._rollup.to_row() if self._rollup.n else None
        self._rollup = _Rollup(now)
        return row


def handshake() -> dict[str, Any]:
    """Wire contract sent to the client on connect."""
    return {
        "protocol": PROTOCOL_VERSION,
        "blendshapes": BLENDSHAPE_NAMES,
        "gaze_landmarks": GAZE_LANDMARKS,
        "forehead_landmarks": [10, 67, 69, 104, 108, 151, 337, 299, 297, 333],
        "target_fps": settings.target_fps,
        "max_samples_per_batch": settings.max_samples_per_batch,
        "batch_interval_ms": 500,
    }


__all__: Sequence[str] = ["SessionPipeline", "BatchResult", "ProtocolError", "handshake", "PROTOCOL_VERSION"]
