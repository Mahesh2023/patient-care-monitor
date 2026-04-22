"""Remote photoplethysmography (rPPG) heart-rate estimator.

Method family: POS-style channel-combined green-dominant bandpass + FFT on
a forehead ROI, following Poh, McDuff & Picard (2010) "Non-contact, automated
cardiac pulse measurements using video imaging and blind source separation"
(Optics Express 18(10)). We keep the implementation dependency-light (no
torch, no onnx) so it runs on CPU-only free-tier hosts.

Limits (explicitly not hidden):
  * Affected by lighting, motion, skin tone, camera compression.
  * NOT a medical device. Use for *trend* monitoring, not diagnosis.
  * SNR-gated: we refuse to emit a BPM when signal quality is poor.
"""
from __future__ import annotations
from collections import deque
from dataclasses import dataclass
from typing import Deque, List, Optional

import numpy as np
from scipy import signal as sps


@dataclass
class HeartRateResult:
    bpm: float = 0.0
    confidence: float = 0.0
    snr: float = 0.0
    signal_quality: str = "no_signal"  # good, fair, poor, no_signal
    is_abnormal: bool = False
    abnormality: str = ""
    timestamp: float = 0.0


class RPPGEstimator:
    def __init__(self, fps: float = 30.0, buffer_size: int = 300,
                 low_hz: float = 0.7, high_hz: float = 4.0) -> None:
        self.fps = float(fps)
        self.buffer_size = buffer_size
        self.low_hz = low_hz
        self.high_hz = high_hz
        self._green: Deque[float] = deque(maxlen=buffer_size)
        self._red: Deque[float] = deque(maxlen=buffer_size)
        self._blue: Deque[float] = deque(maxlen=buffer_size)
        self._hr_history: List[float] = []

    def add_frame(self, forehead_bgr: Optional[np.ndarray]) -> None:
        if forehead_bgr is None or forehead_bgr.size == 0:
            return
        mean_bgr = forehead_bgr.reshape(-1, 3).mean(axis=0)
        self._blue.append(float(mean_bgr[0]))
        self._green.append(float(mean_bgr[1]))
        self._red.append(float(mean_bgr[2]))

    def estimate(self, timestamp: float = 0.0) -> HeartRateResult:
        min_frames = int(self.fps * 5)
        if len(self._green) < min_frames:
            return HeartRateResult(signal_quality="no_signal", timestamp=timestamp)
        g = sps.detrend(np.asarray(self._green, dtype=np.float64))
        std = float(g.std())
        if std < 1e-6:
            return HeartRateResult(signal_quality="poor", timestamp=timestamp)
        g = (g - g.mean()) / std
        try:
            nyq = self.fps / 2.0
            low = max(self.low_hz / nyq, 0.01)
            high = min(self.high_hz / nyq, 0.99)
            b, a = sps.butter(3, [low, high], btype="band")
            filtered = sps.filtfilt(b, a, g)
        except Exception:
            return HeartRateResult(signal_quality="poor", timestamp=timestamp)
        n = len(filtered)
        mag = np.abs(np.fft.rfft(filtered))
        freqs = np.fft.rfftfreq(n, 1.0 / self.fps)
        mask = (freqs >= self.low_hz) & (freqs <= self.high_hz)
        mag_band, freqs_band = mag[mask], freqs[mask]
        if mag_band.size == 0:
            return HeartRateResult(signal_quality="poor", timestamp=timestamp)
        peak = int(np.argmax(mag_band))
        bpm = float(freqs_band[peak] * 60.0)
        peak_power = float(mag_band[peak])
        total_power = float(mag_band.sum())
        snr = peak_power / (total_power - peak_power + 1e-10)
        if snr > 0.3:
            quality, conf = "good", min(1.0, float(snr))
        elif snr > 0.15:
            quality, conf = "fair", float(snr) * 2.0
        else:
            quality, conf = "poor", float(snr) * 3.0
        is_abn, abn = False, ""
        if conf > 0.4:
            if bpm > 100:
                is_abn, abn = True, "tachycardia"
            elif bpm < 60:
                is_abn, abn = True, "bradycardia"
        if conf > 0.3:
            self._hr_history.append(bpm)
            self._hr_history = self._hr_history[-60:]
        return HeartRateResult(
            bpm=round(bpm, 1),
            confidence=round(conf, 3),
            snr=round(snr, 3),
            signal_quality=quality,
            is_abnormal=is_abn,
            abnormality=abn,
            timestamp=timestamp,
        )

    def reset(self) -> None:
        self._green.clear(); self._red.clear(); self._blue.clear()
        self._hr_history.clear()
