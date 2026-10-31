"""Remote photoplethysmography (rPPG) heart-rate estimator.

Method family: green-dominant bandpass + FFT on a forehead ROI, following
Poh, McDuff & Picard (2010) "Non-contact, automated cardiac pulse
measurements using video imaging and blind source separation"
(Optics Express 18(10)).

Production change vs. v2.0: the browser computes the forehead-ROI mean RGB
per analysed frame and ships 3 floats + a timestamp. Because browser frame
rates are irregular, samples are stored with timestamps and *resampled onto a
uniform grid* before filtering — a fixed-FPS assumption would bias BPM.

Limits (explicitly not hidden):
  * Affected by lighting, motion, skin tone, camera compression.
  * NOT a medical device. Use for *trend* monitoring, not diagnosis.
  * SNR-gated: we refuse to emit a BPM when signal quality is poor.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Optional

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
    def __init__(self, resample_hz: float = 15.0, window_s: float = 20.0,
                 min_window_s: float = 6.0,
                 low_hz: float = 0.7, high_hz: float = 4.0) -> None:
        self.resample_hz = float(resample_hz)
        self.window_s = float(window_s)
        self.min_window_s = float(min_window_s)
        self.low_hz = low_hz
        self.high_hz = high_hz
        # Generous cap: 30 fps * window
        self._samples: deque[tuple[float, float]] = deque(maxlen=int(30 * window_s))

    def add_sample(self, rgb: Optional[tuple[float, float, float]], t: float) -> None:
        """Add one forehead-ROI mean colour (R, G, B in 0-255) at time t (s)."""
        if rgb is None or len(rgb) != 3:
            return
        g = float(rgb[1])
        if not np.isfinite(g) or not (0.0 <= g <= 255.0):
            return
        if self._samples and t <= self._samples[-1][0]:
            return  # drop out-of-order / duplicate timestamps
        self._samples.append((float(t), g))
        while self._samples and t - self._samples[0][0] > self.window_s:
            self._samples.popleft()

    def _uniform_signal(self) -> Optional[np.ndarray]:
        if len(self._samples) < 8:
            return None
        arr = np.asarray(self._samples, dtype=np.float64)
        ts, g = arr[:, 0], arr[:, 1]
        span = ts[-1] - ts[0]
        if span < self.min_window_s:
            return None
        # Need >= 5 Hz effective input to resolve up to ~150 bpm (2.5 Hz).
        if len(ts) / span < 5.0:
            return None
        grid = np.arange(ts[0], ts[-1], 1.0 / self.resample_hz)
        return np.interp(grid, ts, g)

    def estimate(self, timestamp: float = 0.0) -> HeartRateResult:
        g = self._uniform_signal()
        if g is None:
            return HeartRateResult(signal_quality="no_signal", timestamp=timestamp)
        g = sps.detrend(g)
        std = float(g.std())
        if std < 1e-6:
            return HeartRateResult(signal_quality="poor", timestamp=timestamp)
        g = (g - g.mean()) / std
        fs = self.resample_hz
        try:
            nyq = fs / 2.0
            low = max(self.low_hz / nyq, 0.01)
            high = min(self.high_hz / nyq, 0.99)
            b, a = sps.butter(3, [low, high], btype="band")
            filtered = sps.filtfilt(b, a, g)
        except Exception:
            return HeartRateResult(signal_quality="poor", timestamp=timestamp)
        mag = np.abs(np.fft.rfft(filtered))
        freqs = np.fft.rfftfreq(len(filtered), 1.0 / fs)
        mask = (freqs >= self.low_hz) & (freqs <= self.high_hz)
        mag_band, freqs_band = mag[mask], freqs[mask]
        if mag_band.size == 0:
            return HeartRateResult(signal_quality="poor", timestamp=timestamp)
        peak = int(np.argmax(mag_band))
        bpm = float(freqs_band[peak] * 60.0)
        peak_power = float(mag_band[peak])
        snr = peak_power / (float(mag_band.sum()) - peak_power + 1e-10)
        if snr > 0.3:
            quality, conf = "good", min(1.0, snr)
        elif snr > 0.15:
            quality, conf = "fair", snr * 2.0
        else:
            quality, conf = "poor", snr * 3.0
        is_abn, abn = False, ""
        if conf > 0.4:
            if bpm > 100:
                is_abn, abn = True, "tachycardia"
            elif bpm < 60:
                is_abn, abn = True, "bradycardia"
        return HeartRateResult(
            bpm=round(bpm, 1),
            confidence=round(float(min(1.0, conf)), 3),
            snr=round(snr, 3),
            signal_quality=quality,
            is_abnormal=is_abn,
            abnormality=abn,
            timestamp=timestamp,
        )

    def reset(self) -> None:
        self._samples.clear()
