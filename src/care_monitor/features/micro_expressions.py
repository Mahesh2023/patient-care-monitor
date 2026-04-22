"""Micro-expression detection via AU-spike temporal model (<500ms events).

This is a simplified, transparent version of the model used in
Sălăgean, Leba & Ionica (2025) — "Real-Time Micro-Expression Recognition
with Action Units and GPT-Based Reasoning" (Applied Sciences 15(12):6417) —
which reports 93.3% accuracy on CASME II by combining AU spikes with LLM
reasoning.

We maintain a rolling per-AU baseline (median of last N frames) and flag a
micro-event whenever an AU deviates > k·MAD for 1-15 frames, then returns
within one frame. This is deliberately rule-based so every alert is
inspectable for clinical audit.
"""
from __future__ import annotations
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Deque, Dict, List

import numpy as np


@dataclass
class MicroEvent:
    au: str
    peak_intensity: float
    duration_ms: float
    timestamp: float


class MicroExpressionDetector:
    def __init__(self, baseline_window: int = 60, k_mad: float = 4.0,
                 min_frames: int = 1, max_frames: int = 15,
                 frame_ms: float = 100.0) -> None:
        self.baseline_window = baseline_window
        self.k_mad = k_mad
        self.min_frames = min_frames
        self.max_frames = max_frames
        self.frame_ms = frame_ms
        self._history: Dict[str, Deque[float]] = defaultdict(
            lambda: deque(maxlen=baseline_window))
        self._active: Dict[str, Dict] = {}

    def _robust_threshold(self, au: str) -> float:
        hist = np.asarray(self._history[au], dtype=np.float64)
        if hist.size < 10:
            return 0.25  # conservative default until we have a baseline
        med = float(np.median(hist))
        mad = float(np.median(np.abs(hist - med))) + 1e-6
        return med + self.k_mad * 1.4826 * mad  # 1.4826 -> MAD-to-sigma for Gaussian

    def add_frame(self, aus: Dict[str, float]) -> List[MicroEvent]:
        events: List[MicroEvent] = []
        now = time.time()
        for au, v in aus.items():
            self._history[au].append(v)
            thresh = self._robust_threshold(au)
            if au in self._active:
                state = self._active[au]
                state["frames"] += 1
                state["peak"] = max(state["peak"], v)
                if v < thresh or state["frames"] > self.max_frames:
                    if self.min_frames <= state["frames"] <= self.max_frames:
                        events.append(MicroEvent(
                            au=au,
                            peak_intensity=state["peak"],
                            duration_ms=state["frames"] * self.frame_ms,
                            timestamp=now,
                        ))
                    del self._active[au]
            elif v > thresh:
                self._active[au] = {"frames": 1, "peak": v, "t0": now}
        return events

    def reset_baseline(self) -> None:
        self._history.clear()
        self._active.clear()
