"""FACS Action Units from MediaPipe 52 ARKit blendshapes.

Rationale:
  MediaPipe's ARKit-compatible blendshape coefficients provide a stable,
  near-real-time estimate of facial muscle activations that align with
  specific FACS Action Units. We apply:
    (1) a bilateral-average mapping from blendshape -> AU,
    (2) per-AU amplification (empirically calibrated against
        Sălăgean et al. 2025 benchmark recommendations), and
    (3) exponential temporal smoothing to suppress jitter.

This avoids training any black-box emotion CNN and keeps every downstream
score fully inspectable — a hard requirement for clinical deployment.
"""
from __future__ import annotations
from collections import deque
from typing import Deque, Dict, List, Set

import numpy as np

BLENDSHAPE_TO_AU: Dict[str, List[str]] = {
    "AU1":  ["browInnerUp"],
    "AU2":  ["browOuterUpLeft", "browOuterUpRight"],
    "AU4":  ["browDownLeft", "browDownRight"],
    "AU5":  ["eyeWideLeft", "eyeWideRight"],
    "AU6":  ["cheekSquintLeft", "cheekSquintRight"],
    "AU7":  ["eyeSquintLeft", "eyeSquintRight"],
    "AU9":  ["noseSneerLeft", "noseSneerRight"],
    "AU10": ["mouthUpperUpLeft", "mouthUpperUpRight"],
    "AU12": ["mouthSmileLeft", "mouthSmileRight"],
    "AU14": ["mouthDimpleLeft", "mouthDimpleRight"],
    "AU15": ["mouthFrownLeft", "mouthFrownRight"],
    "AU17": ["mouthShrugLower"],
    "AU20": ["mouthStretchLeft", "mouthStretchRight"],
    "AU23": ["mouthPressLeft", "mouthPressRight"],
    "AU24": ["mouthPucker"],
    "AU25": ["mouthClose"],           # inverted downstream
    "AU26": ["jawOpen"],
    "AU28": ["mouthRollLower", "mouthRollUpper"],
    "AU43": ["eyeLookDownLeft", "eyeLookDownRight"],
    "AU45": ["eyeBlinkLeft", "eyeBlinkRight"],
}

# Per-AU signal amplification, clipped to [0,1]. Values < 1 attenuate.
AU_AMPLIFICATION: Dict[str, float] = {
    "AU1": 2.0, "AU2": 1.8, "AU4": 2.0, "AU5": 2.0, "AU6": 2.0, "AU7": 3.0,
    "AU9": 3.0, "AU10": 2.5, "AU12": 3.0, "AU14": 2.2, "AU15": 3.0,
    "AU17": 2.0, "AU20": 3.0, "AU23": 2.0, "AU24": 2.0, "AU25": 1.0,
    "AU26": 2.5, "AU28": 1.5, "AU43": 1.5, "AU45": 1.0,
}

# Activation threshold (Sălăgean et al. 2025 use 0.15 for CASME II).
AU_THRESHOLD: float = 0.15


def extract_action_units(blendshapes) -> Dict[str, float]:
    """Blendshapes: iterable of MediaPipe Category objects (category_name, score)."""
    bs = {b.category_name: float(b.score) for b in blendshapes}
    out: Dict[str, float] = {}
    for au, names in BLENDSHAPE_TO_AU.items():
        vals = [bs.get(n, 0.0) for n in names]
        score = float(np.mean(vals)) if vals else 0.0
        if au == "AU25":  # mouthClose is inverted (high -> lips together)
            score = 1.0 - score
        score *= AU_AMPLIFICATION.get(au, 1.0)
        out[au] = float(min(1.0, max(0.0, score)))
    return out


def active_aus(aus: Dict[str, float], thresh: float = AU_THRESHOLD) -> Set[str]:
    return {k for k, v in aus.items() if v > thresh}


class TemporalSmoother:
    """Exponential moving average + sliding window.

    EMA update:  s_t = alpha * x_t + (1 - alpha) * s_{t-1}
    Lower alpha => smoother, slower to respond.
    """

    def __init__(self, alpha: float = 0.3, window_size: int = 5) -> None:
        self.alpha = float(np.clip(alpha, 0.05, 0.95))
        self.window_size = window_size
        self.history: Deque[Dict[str, float]] = deque(maxlen=window_size)
        self.current: Dict[str, float] = {}

    def update(self, new_aus: Dict[str, float]) -> Dict[str, float]:
        self.history.append(dict(new_aus))
        if not self.current:
            self.current = dict(new_aus)
            return dict(self.current)
        for au, v in new_aus.items():
            prev = self.current.get(au, v)
            self.current[au] = self.alpha * v + (1.0 - self.alpha) * prev
        # Decay AUs that dropped out of this frame
        for au in list(self.current.keys()):
            if au not in new_aus:
                self.current[au] *= (1.0 - self.alpha)
        return dict(self.current)

    def reset(self) -> None:
        self.history.clear()
        self.current.clear()
