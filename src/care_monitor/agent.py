"""CareMonitorAgent — orchestrates perception -> features -> inference.

One frame in, one `FrameAnalysis` out. Thread-unsafe — use one agent per
session (the session registry in `dashboard/server.py` handles this).
"""
from __future__ import annotations
import json
import sys
import time
from collections import deque
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Deque, Dict, List, Optional

import numpy as np

# Add project root to import old modules
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from .config import settings
from .logging_utils import get_logger
from .perception.face_mesh import FacePerception
from .perception.head_pose import head_pose_from_matrix
from .perception.iris_gaze import estimate_gaze
from .features.action_units import (
    AU_THRESHOLD, TemporalSmoother, active_aus, extract_action_units,
)
from .features.blink import BlinkTracker
from .features.micro_expressions import MicroEvent, MicroExpressionDetector
from .features.pain import PainAssessment, PainLevel, PSPIDetector
from .features.rppg import HeartRateResult, RPPGEstimator
from .inference.distress_state import DistressState, infer_distress
from .inference.alerts import Alert, AlertEngine, AlertLevel
from .inference.llm_reasoner import LLMReasoner

# Import old modules for multimodal support
from modules.voice_analyzer import VoiceAnalyzer, VoiceAnalysisResult
from modules.text_sentiment import TextSentimentAnalyzer, SentimentResult

log = get_logger(__name__)


# Forehead landmark indices on the MediaPipe 478-mesh — a stable patch
# between the brows and hairline, best SNR for rPPG.
FOREHEAD_IDX = [10, 67, 69, 104, 108, 151, 337, 299, 297, 333]


@dataclass
class FrameAnalysis:
    ts: float
    face_detected: bool = False
    action_units: Dict[str, float] = field(default_factory=dict)
    active_aus: List[str] = field(default_factory=list)
    head_pose: Dict[str, float] = field(default_factory=dict)
    gaze: Dict[str, float] = field(default_factory=dict)
    blink: bool = False
    blink_rpm: float = 0.0
    micro_events: List[Dict[str, Any]] = field(default_factory=list)
    pain: Dict[str, Any] = field(default_factory=dict)
    heart_rate: Dict[str, Any] = field(default_factory=dict)
    voice: Dict[str, Any] = field(default_factory=dict)
    text: Dict[str, Any] = field(default_factory=dict)
    distress: Dict[str, Any] = field(default_factory=dict)
    alerts: List[Dict[str, Any]] = field(default_factory=list)
    clinical_summary: str = ""  # LLM output
    fps: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), default=str)


class CareMonitorAgent:
    def __init__(self, session_id: str = "default",
                 log_dir: Optional[Path] = None) -> None:
        self.session_id = session_id
        self.perception = FacePerception()
        self.au_smoother = TemporalSmoother(alpha=0.35, window_size=5)
        self.blink = BlinkTracker()
        self.micro = MicroExpressionDetector(frame_ms=1000.0 / settings.target_fps)
        self.pain = PSPIDetector(
            mild=settings.pspi_mild_threshold,
            moderate=settings.pspi_moderate_threshold,
            severe=settings.pspi_severe_threshold,
        )
        self.rppg = RPPGEstimator(
            fps=settings.rppg_fps,
            buffer_size=settings.rppg_buffer_frames,
            low_hz=settings.rppg_bandpass_low_hz,
            high_hz=settings.rppg_bandpass_high_hz,
        )
        self.voice = VoiceAnalyzer(sample_rate=16000)
        self.text = TextSentimentAnalyzer()
        self.alerts = AlertEngine(
            cooldown_s=settings.alert_cooldown_seconds,
            consecutive=settings.alert_consecutive_frames,
        )
        self.reasoner = LLMReasoner()
        self.log_dir = log_dir
        if self.log_dir:
            self.log_dir.mkdir(parents=True, exist_ok=True)

        self._t0 = time.time()
        self._frame_count = 0
        self._history: Deque[str] = deque(maxlen=20)
        self._micro_history: Deque[str] = deque(maxlen=20)
        self._voice_history: Deque[str] = deque(maxlen=10)
        self._text_history: Deque[str] = deque(maxlen=10)

    # ------------------------------------------------------------------
    def analyze_audio(self, audio_samples: np.ndarray, timestamp: float = 0.0) -> Dict[str, Any]:
        """Process audio samples and return voice analysis result."""
        try:
            result = self.voice.analyze(audio_samples, timestamp)
            self._voice_history.append(f"{result.vocal_state.value} (v={result.valence:.2f}, a={result.arousal:.2f})")
            return {
                "vocal_state": result.vocal_state.value,
                "arousal": result.arousal,
                "valence": result.valence,
                "confidence": result.confidence,
                "pitch_mean": result.features.pitch_mean if result.features else 0.0,
                "energy_mean": result.features.energy_mean if result.features else 0.0,
                "is_voiced": result.features.is_voiced if result.features else False,
            }
        except Exception as e:
            log.warning(f"Voice analysis error: {e}")
            return {}

    def analyze_text(self, text_input: str, timestamp: float = 0.0) -> Dict[str, Any]:
        """Process text input and return sentiment analysis result."""
        try:
            result = self.text.analyze(text_input, timestamp)
            self._text_history.append(f"pain={result.pain_mentioned}, distress={result.distress_mentioned}")
            return {
                "valence": result.valence,
                "arousal": result.arousal,
                "pain_mentioned": result.pain_mentioned,
                "distress_mentioned": result.distress_mentioned,
                "key_terms": result.key_terms,
                "confidence": result.confidence,
            }
        except Exception as e:
            log.warning(f"Text analysis error: {e}")
            return {}

    # ------------------------------------------------------------------
    def analyze(self, frame_bgr: np.ndarray, 
                audio_samples: Optional[np.ndarray] = None,
                text_input: Optional[str] = None) -> FrameAnalysis:
        self._frame_count += 1
        ts_ms = int((time.time() - self._t0) * 1000)
        result = FrameAnalysis(ts=time.time())

        try:
            mp_result = self.perception.process(frame_bgr, ts_ms)
        except Exception as e:
            log.error(f"Perception error on frame {self._frame_count}: {e}")
            return result

        if not mp_result.face_landmarks:
            return result
        result.face_detected = True
        landmarks = mp_result.face_landmarks[0]
        blendshapes = mp_result.face_blendshapes[0] if mp_result.face_blendshapes else []

        # --- AUs + smoothing ---
        raw_aus = extract_action_units(blendshapes)
        aus = self.au_smoother.update(raw_aus)
        result.action_units = {k: round(v, 3) for k, v in aus.items()}
        result.active_aus = sorted(active_aus(aus))

        # --- head pose + gaze + blink ---
        if mp_result.facial_transformation_matrixes:
            result.head_pose = head_pose_from_matrix(mp_result.facial_transformation_matrixes[0])
        result.gaze = estimate_gaze(landmarks)
        result.blink = self.blink.update(aus.get("AU45", 0.0))
        result.blink_rpm = round(self.blink.rate_per_minute(), 1)

        # --- micro-expressions ---
        events = self.micro.add_frame(aus)
        result.micro_events = [
            {"au": e.au, "peak": round(e.peak_intensity, 3),
             "duration_ms": round(e.duration_ms, 0)}
            for e in events
        ]
        for e in events:
            self._micro_history.append(f"{e.au}({e.duration_ms:.0f}ms)")

        # --- pain (PSPI) ---
        pain_a = self.pain.assess(aus, timestamp=result.ts)
        result.pain = {
            "pspi": pain_a.pspi, "pspi_raw": pain_a.pspi_raw,
            "level": pain_a.level.value, "confidence": pain_a.confidence,
            "trend": pain_a.trend, "contributing_aus": pain_a.contributing_aus,
        }

        # --- rPPG (optional — needs forehead ROI) ---
        hr_result = self._update_rppg(frame_bgr, landmarks, result.ts)
        if hr_result:
            result.heart_rate = {
                "bpm": hr_result.bpm, "confidence": hr_result.confidence,
                "snr": hr_result.snr, "quality": hr_result.signal_quality,
                "is_abnormal": hr_result.is_abnormal,
                "abnormality": hr_result.abnormality,
            }

        # --- voice analysis (optional) ---
        voice_arousal = 0.5
        voice_valence = 0.5
        if audio_samples is not None:
            voice_result = self.analyze_audio(audio_samples, result.ts)
            if voice_result:
                result.voice = voice_result
                voice_arousal = voice_result.get("arousal", 0.5)
                voice_valence = voice_result.get("valence", 0.5)

        # --- text sentiment (optional) ---
        text_arousal = 0.5
        text_valence = 0.5
        text_pain_mentioned = False
        text_distress_mentioned = False
        if text_input is not None and text_input.strip():
            text_result = self.analyze_text(text_input, result.ts)
            if text_result:
                result.text = text_result
                text_arousal = text_result.get("arousal", 0.5)
                text_valence = text_result.get("valence", 0.5)
                text_pain_mentioned = text_result.get("pain_mentioned", False)
                text_distress_mentioned = text_result.get("distress_mentioned", False)

        # --- dimensional distress state (incorporating voice/text) ---
        distress = infer_distress(
            aus=aus, head_pose=result.head_pose, gaze=result.gaze,
            blink_rpm=result.blink_rpm, pain=pain_a,
            heart_rate_bpm=hr_result.bpm if hr_result else 0.0,
            timestamp=result.ts,
        )
        
        # Adjust comfort/arousal based on voice/text if available
        if audio_samples is not None:
            # Blend voice arousal/valence into distress state
            distress.arousal = (distress.arousal + voice_arousal) / 2.0
            distress.comfort = (distress.comfort + voice_valence) / 2.0
            if result.voice and result.voice.get("vocal_state") in ["distressed", "crying", "moaning"]:
                distress.observations.append(f"vocal distress detected: {result.voice.get('vocal_state')}")
        
        if text_input and text_input.strip():
            # Blend text arousal/valence into distress state
            distress.arousal = (distress.arousal + text_arousal) / 2.0
            distress.comfort = (distress.comfort + text_valence) / 2.0
            if text_pain_mentioned:
                distress.observations.append("text mentions pain-related terms")
            if text_distress_mentioned:
                distress.observations.append("text mentions distress-related terms")
        
        # Clamp values
        distress.comfort = max(0.0, min(1.0, distress.comfort))
        distress.arousal = max(0.0, min(1.0, distress.arousal))
        result.distress = {
            "comfort": distress.comfort, "arousal": distress.arousal,
            "pain": distress.pain, "engagement": distress.engagement,
            "tag": distress.behavioural_tag, "confidence": distress.confidence,
            "observations": distress.observations,
        }

        # --- alerts (cooldown-gated) ---
        fired = self.alerts.evaluate(distress, pain_a, hr_result)
        result.alerts = [
            {"key": a.key, "level": a.level.value, "reason": a.reason,
             "evidence": a.evidence, "ts": a.timestamp}
            for a in fired
        ]

        # --- LLM clinical summary (cooldown inside) ---
        if self.reasoner.available():
            snapshot = {
                "aus": aus,
                "head_pose": result.head_pose,
                "gaze": result.gaze,
                "blink_rpm": result.blink_rpm,
                "pspi": pain_a.pspi,
                "pain_level": pain_a.level.value,
                "hr_bpm": hr_result.bpm if hr_result else 0.0,
                "hr_quality": hr_result.signal_quality if hr_result else "no_signal",
                "tag": distress.behavioural_tag,
                "observations": distress.observations,
                "micro_events": list(self._micro_history),
                "voice_state": result.voice.get("vocal_state") if result.voice else None,
                "voice_arousal": result.voice.get("arousal") if result.voice else None,
                "text_valence": result.text.get("valence") if result.text else None,
                "text_pain": result.text.get("pain_mentioned") if result.text else None,
                "text_distress": result.text.get("distress_mentioned") if result.text else None,
            }
            try:
                text = self.reasoner.reason(snapshot)
                if text:
                    result.clinical_summary = text
                    self._history.append(text)
            except Exception as e:
                log.warning(f"LLM reason error: {e}")

        # --- fps ---
        elapsed = time.time() - self._t0
        result.fps = round(self._frame_count / elapsed, 2) if elapsed > 0 else 0.0

        # --- optional jsonl logging (numeric only, never frames) ---
        if self.log_dir and self._frame_count % 30 == 0:
            p = self.log_dir / f"{self.session_id}.jsonl"
            with p.open("a") as f:
                f.write(result.to_json() + "\n")

        return result

    # ------------------------------------------------------------------
    def _update_rppg(self, frame_bgr: np.ndarray, landmarks,
                     ts: float) -> Optional[HeartRateResult]:
        try:
            h, w = frame_bgr.shape[:2]
            pts = np.array([[int(landmarks[i].x * w), int(landmarks[i].y * h)]
                            for i in FOREHEAD_IDX if i < len(landmarks)])
            if pts.size == 0:
                return None
            x_min = max(0, int(pts[:, 0].min()) - 5)
            x_max = min(w, int(pts[:, 0].max()) + 5)
            y_min = max(0, int(pts[:, 1].min()) - 10)
            y_max = min(h, int(pts[:, 1].max()) + 5)
            if x_max - x_min < 10 or y_max - y_min < 10:
                return None
            roi = frame_bgr[y_min:y_max, x_min:x_max]
            self.rppg.add_frame(roi)
            return self.rppg.estimate(timestamp=ts)
        except Exception as e:
            log.debug(f"rPPG ROI error: {e}")
            return None

    # ------------------------------------------------------------------
    def reset(self) -> None:
        self.au_smoother.reset()
        self.blink.reset()
        self.micro.reset_baseline()
        self.pain.reset()
        self.rppg.reset()
        self.voice.reset()
        self.text.reset()
        self._voice_history.clear()
        self._text_history.clear()

    def close(self) -> None:
        try:
            self.perception.close()
        except Exception:
            pass
        self.reset()
