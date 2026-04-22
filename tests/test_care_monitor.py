"""Unit tests for the pure-Python components of CARE-MM v2.

We skip anything needing MediaPipe / OpenCV decoding so these pass on any CI.
"""
from __future__ import annotations
import time
import math

import pytest

from src.care_monitor.features.action_units import (
    AU_THRESHOLD, TemporalSmoother, active_aus, extract_action_units,
    BLENDSHAPE_TO_AU,
)
from src.care_monitor.features.blink import BlinkTracker
from src.care_monitor.features.micro_expressions import MicroExpressionDetector
from src.care_monitor.features.pain import PSPIDetector, PainLevel
from src.care_monitor.inference.distress_state import infer_distress
from src.care_monitor.inference.alerts import AlertEngine, AlertLevel
from src.care_monitor.perception.head_pose import head_pose_from_matrix, head_stable


# ----- dummy blendshape record ---------------------------------------
class _BS:
    def __init__(self, name: str, score: float):
        self.category_name = name
        self.score = score


def _make_bs(d: dict):
    return [_BS(k, v) for k, v in d.items()]


# =====================================================================
# Action Units
# =====================================================================
def test_au_extraction_bilateral_average():
    bs = _make_bs({
        "browDownLeft": 0.4, "browDownRight": 0.2,  # AU4 mean 0.3 * amp 2.0
        "mouthSmileLeft": 0.3, "mouthSmileRight": 0.1,  # AU12 mean 0.2 * amp 3.0
    })
    aus = extract_action_units(bs)
    assert math.isclose(aus["AU4"], min(1.0, 0.3 * 2.0), rel_tol=1e-6)
    assert math.isclose(aus["AU12"], min(1.0, 0.2 * 3.0), rel_tol=1e-6)
    assert 0.0 <= aus["AU1"] <= 1.0


def test_au25_is_inverted_from_mouth_close():
    bs = _make_bs({"mouthClose": 0.8})
    aus = extract_action_units(bs)
    # mouthClose=0.8 -> (1-0.8)=0.2 * amp 1.0 = 0.2
    assert math.isclose(aus["AU25"], 0.2, rel_tol=1e-6)


def test_active_aus_threshold():
    aus = {"AU1": 0.5, "AU2": 0.05, "AU4": AU_THRESHOLD, "AU5": AU_THRESHOLD + 0.01}
    act = active_aus(aus)
    assert "AU1" in act
    assert "AU5" in act
    assert "AU2" not in act
    assert "AU4" not in act  # strictly greater than threshold


def test_smoother_ema_converges():
    sm = TemporalSmoother(alpha=0.5, window_size=10)
    out = sm.update({"AU4": 0.0})
    assert out["AU4"] == 0.0
    for _ in range(30):
        out = sm.update({"AU4": 1.0})
    assert out["AU4"] > 0.99


def test_smoother_decays_when_au_missing():
    sm = TemporalSmoother(alpha=0.5, window_size=10)
    sm.update({"AU4": 1.0})
    # Now AU4 is missing — it should decay
    out1 = sm.update({"AU1": 0.1})
    out2 = sm.update({"AU1": 0.1})
    assert out2["AU4"] < out1["AU4"] < 1.0


# =====================================================================
# Blink
# =====================================================================
def test_blink_tracker_fires_once_per_closure():
    bt = BlinkTracker(threshold=0.5, min_gap_s=0.0)
    t0 = 1000.0
    assert bt.update(0.1, now=t0) is False
    assert bt.update(0.8, now=t0 + 0.1) is True
    # Still closed -> no new fire
    assert bt.update(0.9, now=t0 + 0.2) is False
    # Re-open
    assert bt.update(0.1, now=t0 + 0.3) is False
    # Close again
    assert bt.update(0.9, now=t0 + 0.4) is True


def test_blink_rate_projects_to_per_minute():
    bt = BlinkTracker(threshold=0.5, min_gap_s=0.0)
    t0 = 1000.0
    # Simulate 4 blinks in 10 seconds => ~24/min
    for i, t in enumerate([t0, t0 + 3, t0 + 6, t0 + 9]):
        bt.update(0.1, now=t - 0.01)  # open
        bt.update(0.9, now=t)          # close -> fires
    rate = bt.rate_per_minute(now=t0 + 10)
    assert 20 < rate < 30


# =====================================================================
# Micro-expressions
# =====================================================================
def test_micro_detector_flags_isolated_spike():
    det = MicroExpressionDetector(baseline_window=30, k_mad=3.0, frame_ms=100.0)
    # Baseline: mostly near 0
    for _ in range(30):
        det.add_frame({"AU4": 0.02})
    # Short spike (3 frames)
    events = []
    events += det.add_frame({"AU4": 0.7})
    events += det.add_frame({"AU4": 0.65})
    events += det.add_frame({"AU4": 0.6})
    # Return to baseline
    events += det.add_frame({"AU4": 0.02})
    assert any(e.au == "AU4" for e in events)


# =====================================================================
# PSPI pain detector
# =====================================================================
def test_pspi_formula_matches_canonical_equation():
    det = PSPIDetector()
    # AU4=1, AU6=0.4, AU7=0.6, AU9=0.2, AU10=0.5, AU43=0.3
    # => pspi = 5 + max(2,3) + max(1,2.5) + 1.5 = 5 + 3 + 2.5 + 1.5 = 12
    aus = {"AU4": 1.0, "AU6": 0.4, "AU7": 0.6, "AU9": 0.2, "AU10": 0.5, "AU43": 0.3}
    assert math.isclose(det.compute(aus), 12.0, rel_tol=1e-6)


def test_pspi_classifier_thresholds():
    det = PSPIDetector(mild=1.5, moderate=4.0, severe=8.0)
    for pspi, exp in [(0.0, PainLevel.NONE), (2.0, PainLevel.MILD),
                      (5.0, PainLevel.MODERATE), (10.0, PainLevel.SEVERE)]:
        assert det._classify(pspi) == exp


def test_pspi_trend_detection():
    det = PSPIDetector()
    aus_low = {"AU4": 0.0, "AU6": 0.0, "AU7": 0.0, "AU9": 0.0, "AU10": 0.0, "AU43": 0.0}
    for _ in range(3):
        det.assess(aus_low)
    aus_high = {"AU4": 0.8, "AU6": 0.5, "AU7": 0.5, "AU9": 0.5, "AU10": 0.5, "AU43": 0.5}
    r = None
    for _ in range(5):
        r = det.assess(aus_high)
    assert r.trend == "increasing"


# =====================================================================
# Distress inference
# =====================================================================
def test_distress_tags_severe_grimace():
    det = PSPIDetector()
    aus = {"AU4": 1.0, "AU6": 0.8, "AU7": 0.8, "AU9": 0.8, "AU10": 0.8, "AU43": 0.7}
    pain = det.assess(aus)
    # Seed a few more frames to raise confidence
    for _ in range(6):
        pain = det.assess(aus)
    d = infer_distress(aus, {"pitch":0,"yaw":0,"roll":0}, {"averted":False},
                       blink_rpm=15.0, pain=pain)
    assert d.behavioural_tag.startswith("grimace_pattern")
    assert d.pain > 0.5
    assert d.comfort < 0.5


def test_distress_tag_duchenne_smile_no_pain():
    det = PSPIDetector()
    aus = {"AU6": 0.7, "AU12": 0.8}
    pain = det.assess(aus)
    d = infer_distress(aus, {"pitch":0,"yaw":0,"roll":0}, {"averted":False},
                       blink_rpm=15.0, pain=pain)
    assert d.behavioural_tag == "duchenne_smile_pattern"
    assert d.comfort > 0.6


def test_distress_tag_withdrawn_when_all_quiet():
    det = PSPIDetector()
    aus = {}
    pain = det.assess(aus)
    d = infer_distress(aus, {"pitch":0,"yaw":0,"roll":0}, {"averted":True,"h_ratio":0.2},
                       blink_rpm=4.0, pain=pain)
    assert d.behavioural_tag in ("withdrawn_or_disengaged", "gaze_averted")


# =====================================================================
# Alerts (cooldown + consecutive)
# =====================================================================
def _make_severe_pain_assessment():
    from src.care_monitor.features.pain import PainAssessment, PainLevel
    return PainAssessment(
        pspi=12.0, pspi_raw=12.0, level=PainLevel.SEVERE,
        confidence=0.9, contributing_aus={"AU4": 1.0}, trend="stable",
        timestamp=time.time(),
    )


def test_alerts_require_consecutive_frames():
    eng = AlertEngine(cooldown_s=0.0, consecutive=3)
    from src.care_monitor.inference.distress_state import DistressState
    d = DistressState(comfort=0.5, confidence=0.8)
    pain = _make_severe_pain_assessment()
    assert eng.evaluate(d, pain, hr=None) == []
    assert eng.evaluate(d, pain, hr=None) == []
    fired = eng.evaluate(d, pain, hr=None)
    assert len(fired) == 1
    assert fired[0].level == AlertLevel.URGENT
    assert fired[0].key == "severe_pain"


def test_alerts_respect_cooldown():
    eng = AlertEngine(cooldown_s=60.0, consecutive=1)
    from src.care_monitor.inference.distress_state import DistressState
    d = DistressState(comfort=0.5, confidence=0.8)
    pain = _make_severe_pain_assessment()
    first = eng.evaluate(d, pain, hr=None)
    second = eng.evaluate(d, pain, hr=None)
    assert len(first) == 1
    assert second == []   # inside cooldown


# =====================================================================
# Head pose
# =====================================================================
def test_head_pose_identity_is_zero():
    import numpy as np
    m = np.eye(4, dtype=np.float64)
    hp = head_pose_from_matrix(m)
    assert abs(hp["pitch"]) < 1e-6
    assert abs(hp["yaw"]) < 1e-6
    assert abs(hp["roll"]) < 1e-6
    assert head_stable(hp)


def test_head_pose_unstable_when_extreme():
    assert not head_stable({"pitch": 30, "yaw": 5, "roll": 0})
    assert not head_stable({"pitch": 0, "yaw": 45, "roll": 0})
