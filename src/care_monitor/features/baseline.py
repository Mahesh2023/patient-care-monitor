"""Per-patient neutral-face baseline for Action Units.

Human pain coders adjust to each person's resting face (Rezaei et al. 2021,
IEEE JBHI — dementia pain monitoring with reference/target pairs), and
personalised models consistently outperform population models (Xu & de Sa,
EMBC 2021; Martinez et al., CVPRW 2017). Clinical systems use a short
start-up "baseline stabilisation" phase to capture each patient's resting
pattern under the current camera conditions (PACU facial pain system,
Anesth Pain Med 2025).

Approach (transparent, no training): collect AU intensities for the first
`seconds` of face-present video, take the per-AU median as the neutral
offset, and re-scale  au' = clip((au - b) / (1 - b), 0, 1).

Safety: offsets are capped (default 0.30) so a patient who is already
grimacing during calibration cannot "zero out" a pain expression.
"""
from __future__ import annotations

import numpy as np


class AUBaseline:
    def __init__(self, seconds: float = 20.0, cap: float = 0.30, min_samples: int = 40,
                 baseline: dict[str, float] | None = None) -> None:
        self.seconds, self.cap, self.min_samples = seconds, cap, min_samples
        self.baseline: dict[str, float] | None = (
            {k: float(min(cap, max(0.0, v))) for k, v in baseline.items()} if baseline is not None else None)
        self._buf: list[dict[str, float]] = []
        self._t0: float | None = None
        self._progress = 0.0
        self.fresh = False  # True once a new baseline was computed (to persist)

    @property
    def calibrated(self) -> bool:
        return self.baseline is not None

    @property
    def progress(self) -> float:
        return 1.0 if self.calibrated else self._progress

    def recalibrate(self) -> None:
        self.baseline, self._buf, self._t0, self.fresh, self._progress = None, [], None, False, 0.0

    def update(self, aus: dict[str, float], t: float) -> float:
        """Feed raw AUs during calibration; returns calibration progress 0..1."""
        if self.calibrated:
            return 1.0
        if self._t0 is None:
            self._t0 = t
        self._buf.append(aus)
        prog = min((t - self._t0) / self.seconds, len(self._buf) / self.min_samples)
        self._progress = float(min(0.99, prog))
        if prog >= 1.0:
            keys = set().union(*self._buf)
            self.baseline = {k: float(min(self.cap, np.median([a.get(k, 0.0) for a in self._buf])))
                             for k in sorted(keys)}
            self._buf, self.fresh = [], True
            return 1.0
        return float(prog)

    def adjust(self, aus: dict[str, float]) -> dict[str, float]:
        if not self.baseline:
            return aus
        out = {}
        for k, v in aus.items():
            b = self.baseline.get(k, 0.0)
            out[k] = float(min(1.0, max(0.0, (v - b) / (1.0 - b)))) if b < 1.0 else 0.0
        return out
