"""Simple iris-based gaze estimation from MediaPipe 478-landmark mesh.

Landmarks 468-477 are the refined iris points. We compute iris-to-eye-corner
horizontal/vertical ratios as a coarse gaze direction signal — robust enough
for "gaze aversion" flagging without needing a calibrated eye tracker.
"""
from __future__ import annotations
from typing import Dict, List

# Left eye outer/inner corner and iris center indices (MediaPipe 478 mesh)
L_EYE_OUTER, L_EYE_INNER = 33, 133
R_EYE_OUTER, R_EYE_INNER = 263, 362
L_IRIS = [468, 469, 470, 471, 472]
R_IRIS = [473, 474, 475, 476, 477]


def _iris_center(lms, idx: List[int]):
    xs = [lms[i].x for i in idx]
    ys = [lms[i].y for i in idx]
    return sum(xs) / len(xs), sum(ys) / len(ys)


def estimate_gaze(lms) -> Dict[str, float]:
    """Return {h_ratio, v_ratio, averted} in normalized coords.

    h_ratio ~ 0.5 means iris centered. <0.35 or >0.65 is sideways gaze.
    """
    try:
        lc = _iris_center(lms, L_IRIS)
        rc = _iris_center(lms, R_IRIS)
        lo, li = lms[L_EYE_OUTER], lms[L_EYE_INNER]
        ro, ri = lms[R_EYE_OUTER], lms[R_EYE_INNER]
        l_h = (lc[0] - lo.x) / max(li.x - lo.x, 1e-6)
        r_h = (rc[0] - ri.x) / max(ro.x - ri.x, 1e-6)
        h_ratio = 0.5 * (l_h + r_h)
        v_ratio = 0.5 * ((lc[1] + rc[1]) - (lo.y + ro.y)) / max(
            0.5 * (abs(li.y - lo.y) + abs(ro.y - ri.y)), 1e-6
        )
        averted = bool(h_ratio < 0.35 or h_ratio > 0.65 or abs(v_ratio) > 0.6)
        return {"h_ratio": float(h_ratio), "v_ratio": float(v_ratio), "averted": averted}
    except Exception:
        return {"h_ratio": 0.5, "v_ratio": 0.0, "averted": False}


def gaze_aversion(gaze: Dict[str, float]) -> bool:
    return bool(gaze.get("averted", False))
