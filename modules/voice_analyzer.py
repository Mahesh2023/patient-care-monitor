"""
Voice Analyzer Module
=====================
Extracts acoustic features from audio for distress/comfort detection.

Scientific Basis:
- Schuller et al. (2018). Speech emotion recognition: two decades in a nutshell.
  Communications of the ACM.
- Pitch (F0), energy, jitter, shimmer are established correlates of emotional arousal.
- High pitch + high energy + irregular patterns correlate with distress.
- Low, steady pitch + moderate energy correlate with calm/comfort states.

Limitations:
- Acoustic features correlate with arousal/valence, not specific emotions.
- Individual variation in voice is large.
- Environment noise affects accuracy significantly.
- This module uses simple signal processing, not deep learning, for transparency.
"""

from dataclasses import dataclass
from typing import List, Optional, Tuple
from enum import Enum
import struct

import numpy as np
from scipy import signal


class VocalState(Enum):
    UNKNOWN = "unknown"
    CALM = "calm"
    NEUTRAL = "neutral"
    DISTRESSED = "distressed"
    CRYING = "crying"
    MOANING = "moaning"
    SILENT = "silent"


@dataclass
class VoiceFeatures:
    """Extracted voice features."""
    pitch_mean: float = 0.0       # Hz
    pitch_std: float = 0.0        # Hz
    energy_mean: float = 0.0      # RMS
    energy_std: float = 0.0
    spectral_centroid: float = 0.0  # Hz
    zero_crossing_rate: float = 0.0
    is_voiced: bool = False
    duration_sec: float = 0.0


@dataclass
class VoiceAnalysisResult:
    """Voice analysis output."""
    features: VoiceFeatures = None
    vocal_state: VocalState = VocalState.UNKNOWN
    arousal: float = 0.5     # 0 = very calm, 1 = very agitated
    valence: float = 0.5     # 0 = very negative, 1 = very positive
    confidence: float = 0.0
    timestamp: float = 0.0

    def __post_init__(self):
        if self.features is None:
            self.features = VoiceFeatures()


class VoiceAnalyzer:
    """
    Analyzes audio for vocal distress indicators.
    Uses pitch (autocorrelation), energy, spectral features.
    """

    def __init__(self, sample_rate: int = 16000):
        self.sample_rate = sample_rate
        self._history: List[VoiceAnalysisResult] = []
        self._max_history = 50

    def _compute_pitch_autocorrelation(self, audio: np.ndarray) -> Tuple[float, float]:
        """
        Estimate pitch using autocorrelation method.
        Returns (mean_pitch_hz, std_pitch_hz).
        """
        frame_size = int(0.03 * self.sample_rate)  # 30ms frames
        hop_size = int(0.01 * self.sample_rate)     # 10ms hop
        pitches = []

        for start in range(0, len(audio) - frame_size, hop_size):
            frame = audio[start:start + frame_size]
            # Apply Hamming window
            frame = frame * np.hamming(len(frame))

            # Autocorrelation
            corr = np.correlate(frame, frame, mode='full')
            corr = corr[len(corr) // 2:]

            # Find pitch period (between 50Hz and 500Hz)
            min_lag = int(self.sample_rate / 500)
            max_lag = int(self.sample_rate / 50)

            if max_lag > len(corr):
                continue

            corr_segment = corr[min_lag:max_lag]
            if len(corr_segment) == 0 or np.max(corr_segment) < 0.3 * corr[0]:
                continue  # Likely unvoiced

            peak_lag = np.argmax(corr_segment) + min_lag
            if peak_lag > 0:
                pitch = self.sample_rate / peak_lag
                pitches.append(pitch)

        if not pitches:
            return (0.0, 0.0)

        return (float(np.mean(pitches)), float(np.std(pitches)))

    def _compute_energy(self, audio: np.ndarray) -> Tuple[float, float]:
        """Compute RMS energy statistics."""
        frame_size = int(0.03 * self.sample_rate)
        hop_size = int(0.01 * self.sample_rate)
        energies = []

        for start in range(0, len(audio) - frame_size, hop_size):
            frame = audio[start:start + frame_size]
            rms = np.sqrt(np.mean(frame ** 2))
            energies.append(rms)

        if not energies:
            return (0.0, 0.0)
        return (float(np.mean(energies)), float(np.std(energies)))

    def _compute_spectral_centroid(self, audio: np.ndarray) -> float:
        """Compute spectral centroid (brightness of sound)."""
        fft = np.fft.rfft(audio)
        magnitude = np.abs(fft)
        freqs = np.fft.rfftfreq(len(audio), 1.0 / self.sample_rate)

        if np.sum(magnitude) < 1e-10:
            return 0.0
        return float(np.sum(freqs * magnitude) / np.sum(magnitude))

    def _compute_zero_crossing_rate(self, audio: np.ndarray) -> float:
        """Zero crossing rate - higher for noisy/unvoiced sounds."""
        signs = np.sign(audio)
        crossings = np.sum(np.abs(np.diff(signs)) > 0)
        return float(crossings / len(audio))

    def _classify_state(self, features: VoiceFeatures) -> Tuple[VocalState, float, float]:
        """
        Classify vocal state from features.
        Returns (state, arousal, valence).

        Based on dimensional emotion model (Russell, 1980):
        - Arousal: calm (low) to excited/agitated (high)
        - Valence: negative (low) to positive (high)
        """
        if not features.is_voiced:
            return (VocalState.SILENT, 0.2, 0.5)

        arousal = 0.5
        valence = 0.5

        # High pitch indicates higher arousal
        if features.pitch_mean > 250:
            arousal += 0.2
        elif features.pitch_mean < 150:
            arousal -= 0.1

        # High pitch variability indicates distress or crying
        if features.pitch_std > 60:
            arousal += 0.15
            valence -= 0.15

        # High energy indicates higher arousal
        if features.energy_mean > 0.1:
            arousal += 0.15
        elif features.energy_mean < 0.02:
            arousal -= 0.1

        # High spectral centroid (brightness) can indicate distress
        if features.spectral_centroid > 2000:
            arousal += 0.1
            valence -= 0.1

        arousal = np.clip(arousal, 0, 1)
        valence = np.clip(valence, 0, 1)

        # Classify state from arousal/valence
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

        return (state, float(arousal), float(valence))

    def analyze(self, audio: np.ndarray, timestamp: float = 0.0) -> VoiceAnalysisResult:
        """
        Analyze an audio segment.

        Args:
            audio: numpy array of audio samples (mono, float32, normalized to [-1, 1])
            timestamp: timestamp in seconds

        Returns:
            VoiceAnalysisResult
        """
        if len(audio) < self.sample_rate * 0.1:  # Less than 100ms
            return VoiceAnalysisResult(timestamp=timestamp, vocal_state=VocalState.SILENT)

        # Normalize
        audio = audio.astype(np.float32)
        max_val = np.max(np.abs(audio))
        if max_val > 0:
            audio = audio / max_val

        # Extract features
        pitch_mean, pitch_std = self._compute_pitch_autocorrelation(audio)
        energy_mean, energy_std = self._compute_energy(audio)
        spectral_centroid = self._compute_spectral_centroid(audio)
        zcr = self._compute_zero_crossing_rate(audio)
        is_voiced = pitch_mean > 50 and energy_mean > 0.005

        features = VoiceFeatures(
            pitch_mean=round(pitch_mean, 1),
            pitch_std=round(pitch_std, 1),
            energy_mean=round(energy_mean, 4),
            energy_std=round(energy_std, 4),
            spectral_centroid=round(spectral_centroid, 1),
            zero_crossing_rate=round(zcr, 4),
            is_voiced=is_voiced,
            duration_sec=len(audio) / self.sample_rate,
        )

        state, arousal, valence = self._classify_state(features)

        # Confidence based on signal quality
        confidence = 0.5
        if is_voiced and energy_mean > 0.01:
            confidence = 0.7
        if is_voiced and energy_mean > 0.05:
            confidence = 0.85

        result = VoiceAnalysisResult(
            features=features,
            vocal_state=state,
            arousal=round(arousal, 2),
            valence=round(valence, 2),
            confidence=round(confidence, 2),
            timestamp=timestamp,
        )

        self._history.append(result)
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]

        return result

    def get_recent_trend(self, n: int = 10) -> dict:
        """Get arousal/valence trend over recent analyses."""
        recent = self._history[-n:]
        if len(recent) < 2:
            return {"arousal_trend": "unknown", "valence_trend": "unknown"}

        arousals = [r.arousal for r in recent]
        valences = [r.valence for r in recent]

        a_diff = arousals[-1] - arousals[0]
        v_diff = valences[-1] - valences[0]

        return {
            "arousal_trend": "increasing" if a_diff > 0.1 else ("decreasing" if a_diff < -0.1 else "stable"),
            "valence_trend": "improving" if v_diff > 0.1 else ("declining" if v_diff < -0.1 else "stable"),
            "mean_arousal": round(np.mean(arousals), 2),
            "mean_valence": round(np.mean(valences), 2),
        }

    def reset(self):
        self._history.clear()
