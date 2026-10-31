"""Voice prosody analysis -> dimensional arousal / valence.

Scientific basis:
- Schuller et al. (2018). Speech emotion recognition: two decades in a nutshell.
  Communications of the ACM.
- Pitch (F0), energy and spectral brightness are established correlates of
  vocal arousal. High pitch + high energy + irregular F0 correlate with distress.

Scaling note: in production the *browser* extracts the low-level features
(see `app/static/js/audio.js`, a 1:1 port of `extract_features`) and ships
~6 floats per second instead of 32 KB/s of raw PCM. The server only runs the
cheap rule-based classifier (`classify`). `analyze` (raw samples) is kept for
offline use and parity tests.

Limitations: acoustic features correlate with arousal/valence, not specific
emotions; individual variation and room noise are large.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any
from collections.abc import Mapping

import numpy as np

logger = logging.getLogger(__name__)


class VocalState(str, Enum):
    UNKNOWN = "unknown"
    CALM = "calm"
    NEUTRAL = "neutral"
    DISTRESSED = "distressed"
    CRYING = "crying"
    MOANING = "moaning"
    SILENT = "silent"


@dataclass
class VoiceFeatures:
    pitch_mean: float = 0.0          # Hz
    pitch_std: float = 0.0           # Hz
    energy_mean: float = 0.0         # RMS of peak-normalised signal
    energy_std: float = 0.0
    spectral_centroid: float = 0.0   # Hz
    zero_crossing_rate: float = 0.0
    duration_sec: float = 0.0

    @property
    def is_voiced(self) -> bool:
        return self.pitch_mean > 50 and self.energy_mean > 0.005

    @classmethod
    def from_mapping(cls, m: Mapping[str, Any]) -> VoiceFeatures:
        def f(key: str, lo: float, hi: float) -> float:
            try:
                v = float(m.get(key, 0.0))
            except (TypeError, ValueError):
                return 0.0
            return float(min(hi, max(lo, v))) if np.isfinite(v) else 0.0
        return cls(
            pitch_mean=f("pitch_mean", 0, 1000),
            pitch_std=f("pitch_std", 0, 1000),
            energy_mean=f("energy_mean", 0, 1),
            energy_std=f("energy_std", 0, 1),
            spectral_centroid=f("spectral_centroid", 0, 24000),
            zero_crossing_rate=f("zero_crossing_rate", 0, 1),
            duration_sec=f("duration_sec", 0, 10),
        )


@dataclass
class VoiceAnalysisResult:
    vocal_state: VocalState = VocalState.UNKNOWN
    arousal: float = 0.5
    valence: float = 0.5
    confidence: float = 0.0
    features: VoiceFeatures | None = None

    def to_dict(self) -> dict[str, Any]:
        f = self.features or VoiceFeatures()
        return {
            "vocal_state": self.vocal_state.value,
            "arousal": self.arousal,
            "valence": self.valence,
            "confidence": self.confidence,
            "pitch_mean": f.pitch_mean,
            "energy_mean": f.energy_mean,
            "is_voiced": f.is_voiced,
        }


def extract_features(audio: np.ndarray, sample_rate: int = 16000) -> VoiceFeatures:
    """Reference implementation of the browser-side feature extractor."""
    audio = np.asarray(audio, dtype=np.float32)
    if audio.size < sample_rate * 0.1:
        return VoiceFeatures(duration_sec=audio.size / sample_rate)
    peak = float(np.max(np.abs(audio)))
    if peak > 0:
        audio = audio / peak
    frame, hop = int(0.03 * sample_rate), int(0.01 * sample_rate)
    min_lag, max_lag = int(sample_rate / 500), int(sample_rate / 50)
    window = np.hamming(frame)
    pitches, energies = [], []
    for start in range(0, len(audio) - frame, hop):
        seg = audio[start:start + frame]
        energies.append(float(np.sqrt(np.mean(seg ** 2))))
        w = seg * window
        corr = np.correlate(w, w, mode="full")[frame - 1:]
        if max_lag > len(corr):
            continue
        band = corr[min_lag:max_lag]
        if band.size == 0 or np.max(band) < 0.3 * corr[0]:
            continue
        pitches.append(sample_rate / (int(np.argmax(band)) + min_lag))
    mag = np.abs(np.fft.rfft(audio))
    freqs = np.fft.rfftfreq(len(audio), 1.0 / sample_rate)
    centroid = float(np.sum(freqs * mag) / np.sum(mag)) if np.sum(mag) > 1e-10 else 0.0
    zcr = float(np.sum(np.abs(np.diff(np.sign(audio))) > 0) / len(audio))
    return VoiceFeatures(
        pitch_mean=float(np.mean(pitches)) if pitches else 0.0,
        pitch_std=float(np.std(pitches)) if pitches else 0.0,
        energy_mean=float(np.mean(energies)) if energies else 0.0,
        energy_std=float(np.std(energies)) if energies else 0.0,
        spectral_centroid=centroid,
        zero_crossing_rate=zcr,
        duration_sec=len(audio) / sample_rate,
    )


def _classify_state(features: VoiceFeatures) -> tuple[VocalState, float, float]:
    """Russell (1980) circumplex: arousal (calm->agitated), valence (neg->pos)."""
    if not features.is_voiced:
        return VocalState.SILENT, 0.2, 0.5
    arousal, valence = 0.5, 0.5
    if features.pitch_mean > 250:
        arousal += 0.2
    elif features.pitch_mean < 150:
        arousal -= 0.1
    if features.pitch_std > 60:
        arousal += 0.15
        valence -= 0.15
    if features.energy_mean > 0.1:
        arousal += 0.15
    elif features.energy_mean < 0.02:
        arousal -= 0.1
    if features.spectral_centroid > 2000:
        arousal += 0.1
        valence -= 0.1
    arousal = float(np.clip(arousal, 0, 1))
    valence = float(np.clip(valence, 0, 1))
    if arousal > 0.7 and valence < 0.35:
        state = VocalState.DISTRESSED
    elif arousal > 0.6 and valence < 0.4 and features.pitch_std > 50:
        state = VocalState.CRYING
    elif arousal > 0.5 and valence < 0.4:
        state = VocalState.MOANING
    elif arousal < 0.4:
        state = VocalState.CALM
    else:
        state = VocalState.NEUTRAL
    return state, arousal, valence


def classify(features: VoiceFeatures) -> VoiceAnalysisResult:
    state, arousal, valence = _classify_state(features)
    confidence = 0.5
    if features.is_voiced and features.energy_mean > 0.05:
        confidence = 0.85
    elif features.is_voiced and features.energy_mean > 0.01:
        confidence = 0.7
    return VoiceAnalysisResult(
        vocal_state=state,
        arousal=round(arousal, 2),
        valence=round(valence, 2),
        confidence=round(confidence, 2),
        features=features,
    )


def analyze(audio: np.ndarray, sample_rate: int = 16000) -> VoiceAnalysisResult:
    try:
        return classify(extract_features(audio, sample_rate))
    except Exception as e:  # pragma: no cover - defensive
        logger.error("voice analysis failed: %s", e)
        return VoiceAnalysisResult()


__all__ = [
    "VocalState", "VoiceFeatures", "VoiceAnalysisResult",
    "extract_features", "classify", "analyze",
]
