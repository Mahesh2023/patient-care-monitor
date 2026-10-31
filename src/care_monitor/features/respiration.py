"""Camera-based respiratory rate from two complementary face signals.

1. Breathing-induced head motion: vertical translation of MediaPipe's facial
   transformation matrix (cm). Respiration produces small periodic head/
   shoulder movement (e.g. Samsung Research 2023: facial motion + rPPG fusion,
   MAE 1.33 breaths/min).
2. Respiratory modulation of the skin signal: the low-frequency (0.1-0.6 Hz)
   component of forehead brightness (respiratory-induced intensity
   variation; Electronics 2025 14(11):2152, MAE < 1 bpm).

Both are band-limited to 6-36 breaths/min; the source with the more
prominent spectral peak wins (simple late fusion). Large voluntary head
movement invalidates the motion source.

Limits: needs >= 20 s of reasonably still video; talking/eating corrupts the
estimate; not validated for clinical use.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass

import numpy as np
from scipy import signal as sps

FS = 4.0             # resample rate (Hz) — ample for <= 0.6 Hz
LO, HI = 0.1, 0.6    # 6 - 36 breaths/min


@dataclass
class RespirationResult:
    brpm: float = 0.0
    confidence: float = 0.0
    signal_quality: str = "no_signal"  # good, fair, poor, no_signal
    source: str = ""                   # motion | intensity
    is_abnormal: bool = False
    abnormality: str = ""              # tachypnea | bradypnea


def _prominence(x: np.ndarray) -> tuple[float, float]:
    """(peak_hz, peak power / median in-band power)."""
    n_fft = int(2 ** np.ceil(np.log2(max(len(x) * 8, 1024))))
    p = np.abs(np.fft.rfft(x * np.hanning(len(x)), n=n_fft)) ** 2
    f = np.fft.rfftfreq(n_fft, 1.0 / FS)
    m = (f >= LO) & (f <= HI)
    if not m.any():
        return 0.0, 0.0
    pb = p[m]
    i = int(np.argmax(pb))
    return float(f[m][i]), float(pb[i] / (np.median(pb) + 1e-12))


class RespirationEstimator:
    def __init__(self, window_s: float = 32.0, min_window_s: float = 20.0,
                 rr_high: float = 24.0, rr_low: float = 10.0) -> None:
        self.window_s, self.min_window_s = window_s, min_window_s
        self.rr_high, self.rr_low = rr_high, rr_low
        self._s: deque[tuple[float, float, float]] = deque(maxlen=int(30 * window_s))
        self._ba = sps.butter(2, [LO / (FS / 2), HI / (FS / 2)], btype="band")

    def add_sample(self, t: float, ty: float | None, intensity: float | None) -> None:
        if ty is None and intensity is None:
            return
        if self._s and t <= self._s[-1][0]:
            return
        self._s.append((t, np.nan if ty is None else float(ty),
                        np.nan if intensity is None else float(intensity)))
        while self._s and t - self._s[0][0] > self.window_s:
            self._s.popleft()

    def _channel(self, ts: np.ndarray, x: np.ndarray, grid: np.ndarray) -> np.ndarray | None:
        ok = np.isfinite(x)
        if ok.sum() < 0.8 * len(x):
            return None
        y = sps.detrend(np.interp(grid, ts[ok], x[ok]))
        if y.std() < 1e-9:
            return None
        return sps.filtfilt(*self._ba, y)

    def estimate(self) -> RespirationResult:
        if len(self._s) < 40:
            return RespirationResult()
        arr = np.asarray(self._s, dtype=np.float64)
        ts = arr[:, 0]
        if ts[-1] - ts[0] < self.min_window_s:
            return RespirationResult()
        grid = np.arange(ts[0], ts[-1], 1.0 / FS)
        cands = []
        ty = arr[:, 1]
        # Voluntary movement (> ~1.5 cm std) swamps mm-scale breathing motion.
        if np.isfinite(ty).any() and np.nanstd(ty) < 1.5:
            y = self._channel(ts, ty, grid)
            if y is not None:
                cands.append(("motion", *_prominence(y)))
        y = self._channel(ts, arr[:, 2], grid)
        if y is not None:
            cands.append(("intensity", *_prominence(y)))
        if not cands:
            return RespirationResult(signal_quality="poor")
        src, f0, prom = max(cands, key=lambda c: c[2])
        brpm = f0 * 60.0
        quality = "good" if prom >= 8 else "fair" if prom >= 4 else "poor"
        conf = float(np.clip((prom - 2.0) / 10.0, 0.0, 1.0))
        is_abn, abn = False, ""
        if quality != "poor":
            if brpm > self.rr_high:
                is_abn, abn = True, "tachypnea"
            elif brpm < self.rr_low:
                is_abn, abn = True, "bradypnea"
        return RespirationResult(round(brpm, 1), round(conf, 3), quality, src, is_abn, abn)

    def reset(self) -> None:
        self._s.clear()
