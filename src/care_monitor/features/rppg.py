"""Remote photoplethysmography (rPPG) heart rate: POS + signal-quality gating.

Method: Plane-Orthogonal-to-Skin (POS), Wang, den Brinker, Stuijk & de Haan
(2017) "Algorithmic Principles of Remote PPG", IEEE TBME 64(7):1479-1491.
POS temporally normalises the RGB trace, projects it onto the plane
orthogonal to the skin-tone vector (eliminating intensity/illumination
variation first) and alpha-tunes the two projections. Comparative studies
report it as the most robust classical method across lighting and motion,
and markedly less skin-tone dependent than the green channel alone.

Signal-quality indices (SQIs) — we refuse to report a BPM when they fail:
  * SNR (de Haan & Jeanne 2013): power within +-0.1 Hz of the HR peak and its
    first harmonic vs. the rest of the 0.7-4 Hz band, in dB.
  * Disturbance index (Fouad et al.-style DI surge, CinC 2017): fraction of
    samples whose frame-to-frame intensity change exceeds 5x the running
    median — flags motion, illumination jumps and occlusions.
  * Split-half consistency (relative difference of spectral peaks, CinC 2020):
    peak frequency of the first vs. second half of the window must agree.

The browser supplies the forehead-ROI mean RGB per frame with timestamps;
samples are resampled onto a uniform grid (browser frame rates are irregular).

Limits: affected by lighting, motion, skin tone, compression and elevated
heart rates (npj Digit. Med. 2025, CHILL dataset). NOT a medical device.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass

import numpy as np
from scipy import signal as sps

_P = np.array([[0.0, 1.0, -1.0], [-2.0, 1.0, 1.0]])  # POS projection (R, G, B)


@dataclass
class HeartRateResult:
    bpm: float = 0.0
    confidence: float = 0.0
    snr: float = 0.0                 # dB
    signal_quality: str = "no_signal"  # good, fair, poor, no_signal
    motion_fraction: float = 0.0
    consistent: bool = False
    is_abnormal: bool = False
    abnormality: str = ""
    timestamp: float = 0.0


def pos_signal(rgb: np.ndarray, fs: float, win_s: float = 1.6) -> np.ndarray:
    """POS pulse signal from an (N, 3) uniformly sampled RGB trace (Wang 2017, Alg. 1)."""
    n = rgb.shape[0]
    win = max(2, int(np.ceil(win_s * fs)))
    h = np.zeros(n)
    if n < win:
        return h
    # Vectorised over all windows: (K, win, 3) with K = n - win + 1.
    segs = np.lib.stride_tricks.sliding_window_view(rgb, win, axis=0).transpose(0, 2, 1)
    mean = segs.mean(axis=1, keepdims=True)
    cn = segs / np.where(mean > 0, mean, 1.0)
    s = cn @ _P.T                                   # (K, win, 2)
    s1, s2 = s[..., 0], s[..., 1]
    sd2 = s2.std(axis=1, keepdims=True)
    alpha = np.where(sd2 > 1e-12, s1.std(axis=1, keepdims=True) / np.where(sd2 > 1e-12, sd2, 1.0), 0.0)
    hh = s1 + alpha * s2
    hh -= hh.mean(axis=1, keepdims=True)
    for j in range(win):                            # overlap-add (win iterations, not K)
        h[j:j + hh.shape[0]] += hh[:, j]
    return h


def _spectrum(x: np.ndarray, fs: float) -> tuple[np.ndarray, np.ndarray]:
    n_fft = int(2 ** np.ceil(np.log2(max(len(x) * 8, 2048))))
    win = np.hanning(len(x))
    mag = np.abs(np.fft.rfft(x * win, n=n_fft)) ** 2
    return np.fft.rfftfreq(n_fft, 1.0 / fs), mag


def _peak_hz(x: np.ndarray, fs: float, lo: float, hi: float) -> float:
    f, p = _spectrum(x, fs)
    m = (f >= lo) & (f <= hi)
    return float(f[m][np.argmax(p[m])]) if m.any() else 0.0


def snr_db(x: np.ndarray, fs: float, f0: float, lo: float, hi: float, tol: float = 0.1) -> float:
    f, p = _spectrum(x, fs)
    band = (f >= lo) & (f <= hi)
    sig = band & ((np.abs(f - f0) <= tol) | (np.abs(f - 2 * f0) <= tol))
    noise = band & ~sig
    ps, pn = float(p[sig].sum()), float(p[noise].sum())
    return float(10 * np.log10(ps / pn)) if ps > 0 and pn > 0 else -20.0


def disturbance_fraction(intensity: np.ndarray, k: float = 5.0, hist: int = 50) -> float:
    """Fraction of samples with a DI surge (|dI| > k * running median |dI|)."""
    d = np.abs(np.diff(intensity))
    if d.size <= hist:
        return 0.0
    ref = np.median(np.lib.stride_tricks.sliding_window_view(d[:-1], hist), axis=1)
    cur = d[hist:]
    return float(np.mean(cur > k * np.maximum(ref, 1e-3)))


class RPPGEstimator:
    def __init__(self, resample_hz: float = 15.0, window_s: float = 20.0,
                 min_window_s: float = 8.0, low_hz: float = 0.7, high_hz: float = 4.0,
                 hr_high: float = 100.0, hr_low: float = 60.0) -> None:
        self.resample_hz = float(resample_hz)
        self.window_s = float(window_s)
        self.min_window_s = float(min_window_s)
        self.low_hz, self.high_hz = low_hz, high_hz
        self.hr_high, self.hr_low = hr_high, hr_low
        self._samples: deque[tuple[float, float, float, float]] = deque(maxlen=int(30 * window_s))
        nyq = self.resample_hz / 2.0
        self._ba = sps.butter(3, [max(low_hz / nyq, 0.01), min(high_hz / nyq, 0.99)], btype="band")

    def add_sample(self, rgb, t: float) -> None:
        """Add one forehead-ROI mean colour (R, G, B in 0-255) at time t (s)."""
        if rgb is None or len(rgb) != 3:
            return
        r, g, b = (float(v) for v in rgb)
        if not all(np.isfinite(v) and 0.0 < v <= 255.0 for v in (r, g, b)):
            return
        if self._samples and t <= self._samples[-1][0]:
            return  # drop out-of-order / duplicate timestamps
        self._samples.append((float(t), r, g, b))
        while self._samples and t - self._samples[0][0] > self.window_s:
            self._samples.popleft()

    def _uniform(self) -> np.ndarray | None:
        if len(self._samples) < 16:
            return None
        arr = np.asarray(self._samples, dtype=np.float64)
        ts = arr[:, 0]
        span = ts[-1] - ts[0]
        # Need >= 5 Hz effective input to resolve up to ~150 bpm (2.5 Hz).
        if span < self.min_window_s or len(ts) / span < 5.0:
            return None
        grid = np.arange(ts[0], ts[-1], 1.0 / self.resample_hz)
        return np.column_stack([np.interp(grid, ts, arr[:, i]) for i in (1, 2, 3)])

    def estimate(self, timestamp: float = 0.0) -> HeartRateResult:
        rgb = self._uniform()
        if rgb is None:
            return HeartRateResult(signal_quality="no_signal", timestamp=timestamp)
        fs = self.resample_hz
        motion = disturbance_fraction(rgb.mean(axis=1))
        h = sps.detrend(pos_signal(rgb, fs))
        if h.std() < 1e-9:
            return HeartRateResult(signal_quality="poor", motion_fraction=round(motion, 3), timestamp=timestamp)
        try:
            h = sps.filtfilt(*self._ba, h)
        except Exception:
            return HeartRateResult(signal_quality="poor", timestamp=timestamp)

        f0 = _peak_hz(h, fs, self.low_hz, self.high_hz)
        bpm = f0 * 60.0
        snr = snr_db(h, fs, f0, self.low_hz, self.high_hz)
        half = len(h) // 2
        consistent = False
        if half / fs >= 4.0:
            b1 = _peak_hz(h[:half], fs, self.low_hz, self.high_hz) * 60
            b2 = _peak_hz(h[half:], fs, self.low_hz, self.high_hz) * 60
            consistent = abs(b1 - b2) <= 12.0

        if snr >= 3.0 and consistent and motion < 0.1:
            quality = "good"
        elif snr >= 0.0 and motion < 0.2:
            quality = "fair"
        else:
            quality = "poor"
        conf = float(np.clip((snr + 3.0) / 9.0, 0.0, 1.0))
        conf *= (1.0 if consistent else 0.6) * float(np.clip(1.0 - 2.0 * motion, 0.0, 1.0))
        is_abn, abn = False, ""
        if quality != "poor" and conf > 0.4:
            if bpm > self.hr_high:
                is_abn, abn = True, "tachycardia"
            elif bpm < self.hr_low:
                is_abn, abn = True, "bradycardia"
        return HeartRateResult(
            bpm=round(bpm, 1), confidence=round(conf, 3), snr=round(snr, 2),
            signal_quality=quality, motion_fraction=round(motion, 3), consistent=consistent,
            is_abnormal=is_abn, abnormality=abn, timestamp=timestamp,
        )

    def reset(self) -> None:
        self._samples.clear()
