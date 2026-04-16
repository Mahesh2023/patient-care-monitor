"""
Remote Photoplethysmography (rPPG) Module
==========================================
Estimates heart rate from facial skin color changes in video.

Scientific Basis:
- Poh, McDuff & Picard (2010). Non-contact, automated cardiac pulse
  measurements using video imaging and blind source separation.
  Optics Express, 18(10), 10762-10774.
- Verkruysse, Svaasand & Nelson (2008). Remote plethysmographic imaging
  using ambient light. Optics Express.
- The green channel of facial skin video contains the strongest PPG signal
  due to hemoglobin absorption properties.

Method: Green-channel temporal filtering approach.
- Extract mean green channel intensity from forehead ROI per frame
- Bandpass filter (0.7-4.0 Hz = 42-240 bpm)
- FFT to find dominant frequency

Limitations:
- Sensitive to motion artifacts, lighting changes, and skin tone
- Requires relatively stable subject and consistent lighting
- NOT a medical-grade measurement; for monitoring trends only
- Dark skin tones may have lower signal-to-noise ratio
"""

import logging
from collections import deque
from dataclasses import dataclass
from typing import Optional, List

import numpy as np
from scipy import signal as scipy_signal

logger = logging.getLogger(__name__)


@dataclass
class HeartRateResult:
    """Heart rate estimation result."""
    bpm: float = 0.0
    confidence: float = 0.0
    signal_quality: str = "unknown"  # good, fair, poor, no_signal
    is_abnormal: bool = False
    abnormality_type: str = ""  # tachycardia, bradycardia, or empty
    timestamp: float = 0.0


class RPPGEstimator:
    """
    Estimates heart rate from facial video using rPPG.
    Uses green-channel temporal filtering + FFT.
    """

    def __init__(self, fps: float = 30.0, buffer_size: int = 300,
                 bandpass_low: float = 0.7, bandpass_high: float = 4.0):
        """
        Args:
            fps: Camera frames per second
            buffer_size: Number of frames to buffer (~10s at 30fps)
            bandpass_low: Low cutoff Hz (0.7 Hz = 42 bpm)
            bandpass_high: High cutoff Hz (4.0 Hz = 240 bpm)
        """
        self.fps = fps
        self.buffer_size = buffer_size
        self.bandpass_low = bandpass_low
        self.bandpass_high = bandpass_high

        # Signal buffers
        self._green_signal: deque = deque(maxlen=buffer_size)
        self._red_signal: deque = deque(maxlen=buffer_size)
        self._blue_signal: deque = deque(maxlen=buffer_size)
        self._timestamps: deque = deque(maxlen=buffer_size)

        # HR history for trend detection
        self._hr_history: List[float] = []
        self._max_history = 60

    def add_frame(self, forehead_roi: Optional[np.ndarray], timestamp: float = 0.0):
        """
        Add a frame's forehead ROI to the signal buffer.

        Args:
            forehead_roi: BGR image of the forehead region
            timestamp: Frame timestamp in seconds
        """
        try:
            if forehead_roi is None or forehead_roi.size == 0:
                return

            # Compute mean color values across the ROI
            mean_bgr = np.mean(forehead_roi.reshape(-1, 3), axis=0)
            self._blue_signal.append(mean_bgr[0])
            self._green_signal.append(mean_bgr[1])
            self._red_signal.append(mean_bgr[2])
            self._timestamps.append(timestamp)
        except Exception as e:
            logger.warning(f"Error adding frame to rPPG buffer: {e}")

    def estimate_heart_rate(self, timestamp: float = 0.0) -> HeartRateResult:
        """
        Estimate heart rate from buffered signal.
        Requires at least ~5 seconds of data (150 frames at 30fps).
        """
        min_frames = int(self.fps * 5)
        if len(self._green_signal) < min_frames:
            return HeartRateResult(
                signal_quality="no_signal",
                timestamp=timestamp,
            )

        # Convert to numpy arrays
        green = np.array(self._green_signal, dtype=np.float64)

        # Detrend (remove slow baseline drift)
        green = scipy_signal.detrend(green)

        # Normalize
        std = np.std(green)
        if std < 1e-6:
            return HeartRateResult(signal_quality="poor", timestamp=timestamp)
        green = (green - np.mean(green)) / std

        # Bandpass filter
        try:
            nyquist = self.fps / 2.0
            low = self.bandpass_low / nyquist
            high = self.bandpass_high / nyquist

            if high >= 1.0:
                high = 0.99
            if low <= 0:
                low = 0.01

            b, a = scipy_signal.butter(3, [low, high], btype='band')
            filtered = scipy_signal.filtfilt(b, a, green)
        except Exception:
            return HeartRateResult(signal_quality="poor", timestamp=timestamp)

        # FFT
        n = len(filtered)
        fft_vals = np.fft.rfft(filtered)
        fft_magnitude = np.abs(fft_vals)
        freqs = np.fft.rfftfreq(n, 1.0 / self.fps)

        # Only look in physiological range
        valid_mask = (freqs >= self.bandpass_low) & (freqs <= self.bandpass_high)
        valid_freqs = freqs[valid_mask]
        valid_magnitude = fft_magnitude[valid_mask]

        if len(valid_magnitude) == 0:
            return HeartRateResult(signal_quality="poor", timestamp=timestamp)

        # Find dominant frequency
        peak_idx = np.argmax(valid_magnitude)
        peak_freq = valid_freqs[peak_idx]
        bpm = peak_freq * 60.0

        # Signal quality estimation
        peak_power = valid_magnitude[peak_idx]
        total_power = np.sum(valid_magnitude)
        snr = peak_power / (total_power - peak_power + 1e-10)

        if snr > 0.3:
            quality = "good"
            confidence = min(1.0, snr)
        elif snr > 0.15:
            quality = "fair"
            confidence = snr * 2
        else:
            quality = "poor"
            confidence = snr * 3

        # Check for abnormalities
        is_abnormal = False
        abnormality = ""
        if bpm > 100 and confidence > 0.4:
            is_abnormal = True
            abnormality = "tachycardia"
        elif bpm < 60 and confidence > 0.4:
            is_abnormal = True
            abnormality = "bradycardia"

        result = HeartRateResult(
            bpm=round(bpm, 1),
            confidence=round(confidence, 2),
            signal_quality=quality,
            is_abnormal=is_abnormal,
            abnormality_type=abnormality,
            timestamp=timestamp,
        )

        # Track history
        if confidence > 0.3:
            self._hr_history.append(bpm)
            if len(self._hr_history) > self._max_history:
                self._hr_history = self._hr_history[-self._max_history:]

        return result

    def get_hr_trend(self) -> dict:
        """Get heart rate trend."""
        try:
            if len(self._hr_history) < 3:
                return {"trend": "insufficient_data", "mean_bpm": 0.0, "std_bpm": 0.0}

            recent = self._hr_history[-5:]
            mean_bpm = float(np.mean(recent))
            std_bpm = float(np.std(recent))

            if len(self._hr_history) >= 10:
                older = self._hr_history[-10:-5]
                diff = np.mean(recent) - np.mean(older)
                if diff > 5:
                    trend = "increasing"
                elif diff < -5:
                    trend = "decreasing"
                else:
                    trend = "stable"
            else:
                trend = "stable"

            return {
                "trend": trend,
                "mean_bpm": round(mean_bpm, 1),
                "std_bpm": round(std_bpm, 1),
                "latest_bpm": round(self._hr_history[-1], 1),
            }
        except Exception as e:
            logger.error(f"Error computing HR trend: {e}")
            return {"trend": "error", "mean_bpm": 0.0, "std_bpm": 0.0}

    def reset(self):
        self._green_signal.clear()
        self._red_signal.clear()
        self._blue_signal.clear()
        self._timestamps.clear()
        self._hr_history.clear()
