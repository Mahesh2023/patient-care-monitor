"""Blink detection + blink-rate-per-minute from AU45 (eye closure) time series.

Based on Soukupova & Cech (2016) style rising/falling-edge detection,
but applied to MediaPipe's AU45 blendshape instead of EAR landmarks
(gives slightly more stable results on low-res webcam video).
"""
from __future__ import annotations
import time
from collections import deque
from typing import Deque


class BlinkTracker:
    def __init__(self, threshold: float = 0.5, min_gap_s: float = 0.15) -> None:
        self.threshold = threshold
        self.min_gap_s = min_gap_s
        self._closed = False
        self._last_blink_t = 0.0
        self._events: Deque[float] = deque(maxlen=120)  # 2 minutes worth

    def update(self, au45: float, now: float | None = None) -> bool:
        now = time.time() if now is None else now
        fired = False
        if au45 > self.threshold and not self._closed:
            if now - self._last_blink_t > self.min_gap_s:
                self._events.append(now)
                self._last_blink_t = now
                fired = True
            self._closed = True
        elif au45 <= self.threshold * 0.6:
            self._closed = False
        return fired

    def rate_per_minute(self, now: float | None = None) -> float:
        now = time.time() if now is None else now
        window = 60.0
        recent = [t for t in self._events if now - t <= window]
        if not recent:
            return 0.0
        # Project partial window to per-minute
        span = max(now - recent[0], 1.0)
        return len(recent) * (60.0 / span)

    def reset(self) -> None:
        self._events.clear()
        self._closed = False
        self._last_blink_t = 0.0
