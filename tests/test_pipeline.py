"""SessionPipeline, wire protocol, rPPG and voice tests (no network/DB)."""
from __future__ import annotations

import math

import numpy as np
import pytest

from src.care_monitor.features.action_units import BLENDSHAPE_NAMES, action_units_from_vector
from src.care_monitor.features.rppg import RPPGEstimator
from src.care_monitor.features.voice import VocalState, VoiceFeatures, analyze, classify, extract_features
from src.care_monitor.perception.head_pose import head_pose_from_column_major
from src.care_monitor.perception.iris_gaze import GAZE_LANDMARKS
from src.care_monitor.pipeline import ProtocolError, SessionPipeline, handshake

PAIN = {"browDownLeft": 0.5, "browDownRight": 0.5, "eyeSquintLeft": 0.33, "eyeSquintRight": 0.33,
        "noseSneerLeft": 0.33, "noseSneerRight": 0.33, "eyeLookDownLeft": 0.5, "eyeLookDownRight": 0.5}
IDENTITY = [1.0, 0, 0, 0, 0, 1.0, 0, 0, 0, 0, 1.0, 0, 0, 0, 0, 1.0]
LM = [0.30, 0.40, 0.45, 0.40, 0.70, 0.40, 0.55, 0.40] + [0.375, 0.40] * 5 + [0.625, 0.40] * 5


def bs(scores: dict) -> list:
    return [scores.get(n, 0.0) for n in BLENDSHAPE_NAMES]


def sample(t_ms: float, scores: dict | None = None, rgb=None) -> dict:
    if scores is None:
        return {"t": t_ms, "bs": None}
    return {"t": t_ms, "bs": bs(scores), "m": IDENTITY, "lm": LM, "rgb": rgb or [120.0, 100.0, 90.0]}


def test_handshake_contract_matches_wire_sizes():
    h = handshake()
    assert h["blendshapes"] == BLENDSHAPE_NAMES
    assert len(h["gaze_landmarks"]) == len(GAZE_LANDMARKS) == 14
    assert h["protocol"] == 1


def test_vector_au_mapping_equals_named_mapping():
    aus = action_units_from_vector(bs({"browDownLeft": 0.4, "browDownRight": 0.2}))
    assert math.isclose(aus["AU4"], 0.6, rel_tol=1e-6)


def test_column_major_identity_head_pose():
    hp = head_pose_from_column_major(IDENTITY)
    assert all(abs(v) < 1e-9 for v in hp.values())


def test_no_face_batch():
    p = SessionPipeline()
    r = p.process_batch({"samples": [sample(1000), sample(1100)]}, now=1.0)
    assert r.face_detected is False and r.samples == 2 and p.sample_count == 2
    assert r.pain == {} and r.alerts == []


def test_pain_batch_triggers_severe_alert_after_consecutive_frames():
    p = SessionPipeline(baseline={})  # pre-calibrated (zero offsets)
    t0 = 1_700_000_000_000
    alerts = []
    for b in range(4):
        batch = [sample(t0 + (b * 5 + i) * 100, PAIN) for i in range(5)]
        r = p.process_batch({"samples": batch})
        alerts += r.alerts
    assert r.face_detected
    assert r.pain["level"] in ("moderate", "severe")
    assert r.distress["tag"].startswith("grimace_pattern")
    assert any(a["key"] in ("severe_pain", "moderate_pain") for a in alerts)
    assert p.last_snapshot["pspi"] > 4


def test_replayed_samples_are_ignored():
    p = SessionPipeline()
    batch = {"samples": [sample(1000, {}), sample(1100, {})]}
    p.process_batch(batch)
    p.process_batch(batch)
    assert p.sample_count == 2


@pytest.mark.parametrize("bad", [
    {"samples": "nope"},
    {"samples": [{"t": "x"}]},
    {"samples": [{"t": 1, "bs": [0.1, 0.2]}]},
    {"samples": [{"t": 1, "bs": ["a"] * len(BLENDSHAPE_NAMES)}]},
    {"samples": [{"t": 1}] * 1000},
])
def test_protocol_validation(bad):
    with pytest.raises(ProtocolError):
        SessionPipeline().process_batch(bad)


def test_out_of_range_values_are_clipped():
    p = SessionPipeline()
    s = sample(1000, {"browDownLeft": 1.0})
    s["bs"] = [5.0] * len(BLENDSHAPE_NAMES)
    s["rgb"] = [1e9, float("inf"), -5]
    r = p.process_batch({"samples": [s]})
    assert all(0.0 <= v <= 1.0 for v in r.action_units.values())


def test_voice_and_text_fusion():
    p = SessionPipeline()
    r = p.process_batch({
        "samples": [sample(1000, {"mouthSmileLeft": 0.3, "mouthSmileRight": 0.3})],
        "audio": {"pitch_mean": 320, "pitch_std": 80, "energy_mean": 0.2, "spectral_centroid": 2500},
        "text": "she says the pain is terrible, please help",
    })
    assert r.voice["vocal_state"] in ("distressed", "crying", "moaning")
    assert r.text["pain_mentioned"] is True
    assert "note_mentions_pain" in r.distress["observations"]


def test_rollup_emitted_on_force():
    p = SessionPipeline()
    p.process_batch({"samples": [sample(1000, PAIN), sample(1100)]})
    row = p.pop_rollup(force=True)
    assert row["samples"] == 2 and row["face_samples"] == 1 and row["max_pspi"] > 0
    assert p.pop_rollup(force=True) is None


# ---------------------------------------------------------------- rPPG
def test_rppg_recovers_heart_rate_from_irregular_sampling():
    rng = np.random.default_rng(0)
    est = RPPGEstimator(resample_hz=15.0, window_s=20.0)
    bpm = 72.0
    t = 0.0
    while t < 15.0:
        g = 100 + 2.0 * math.sin(2 * math.pi * (bpm / 60) * t) + rng.normal(0, 0.3)
        est.add_sample((120.0, g, 90.0), t)
        t += rng.uniform(1 / 14, 1 / 9)  # jittery 9-14 fps browser timing
    r = est.estimate()
    assert r.signal_quality in ("good", "fair")
    assert abs(r.bpm - bpm) < 6


def test_pos_rejects_common_mode_illumination_flicker():
    """POS (Wang 2017) cancels intensity variation that fools the green channel."""
    rng = np.random.default_rng(1)
    est = RPPGEstimator()
    pulsatile, base = np.array([0.33, 0.77, 0.53]), np.array([150.0, 110.0, 90.0])
    t = 0.0
    while t < 20.0:
        pulse = 0.004 * math.sin(2 * math.pi * 1.2 * t)    # 72 bpm
        flicker = 0.02 * math.sin(2 * math.pi * 1.6 * t)   # 96 bpm lighting flicker, 5x stronger
        est.add_sample(tuple(base * (1 + flicker) + base * pulsatile * pulse + rng.normal(0, 0.15, 3)), t)
        t += rng.uniform(1 / 14, 1 / 10)
    r = est.estimate()
    assert abs(r.bpm - 72) < 4 and r.signal_quality == "good" and r.consistent


def test_rppg_noise_is_gated_as_poor():
    rng = np.random.default_rng(2)
    est = RPPGEstimator()
    t = 0.0
    while t < 20.0:
        est.add_sample(tuple(120 + rng.normal(0, 3, 3)), t)
        t += 0.08
    r = est.estimate()
    assert r.signal_quality in ("poor", "fair") and not r.is_abnormal


def test_rppg_motion_surges_detected():
    rng = np.random.default_rng(3)
    est = RPPGEstimator()
    t, i = 0.0, 0
    while t < 20.0:
        jump = 40.0 if i % 7 == 0 else 0.0   # frequent illumination jumps / occlusions
        est.add_sample(tuple(np.array([150.0, 110.0, 90.0]) + jump + rng.normal(0, 0.1, 3)), t)
        t += 0.08
        i += 1
    r = est.estimate()
    assert r.motion_fraction > 0.1 and r.signal_quality == "poor"


def test_respiration_from_head_motion():
    from src.care_monitor.features.respiration import RespirationEstimator
    rng = np.random.default_rng(4)
    est = RespirationEstimator()
    t = 0.0
    while t < 32.0:
        ty = 0.15 * math.sin(2 * math.pi * (15 / 60) * t) + rng.normal(0, 0.01)   # 15 breaths/min
        est.add_sample(t, ty, 120 + rng.normal(0, 0.5))
        t += 0.1
    r = est.estimate()
    assert abs(r.brpm - 15) < 2 and r.signal_quality in ("good", "fair") and r.source == "motion"
    assert not r.is_abnormal


def test_respiration_tachypnea_flagged():
    from src.care_monitor.features.respiration import RespirationEstimator
    est = RespirationEstimator()
    t = 0.0
    while t < 32.0:
        est.add_sample(t, 0.2 * math.sin(2 * math.pi * (30 / 60) * t), None)
        t += 0.1
    r = est.estimate()
    assert abs(r.brpm - 30) < 2 and r.abnormality == "tachypnea"


def test_baseline_calibration_removes_resting_offset_but_caps():
    from src.care_monitor.features.baseline import AUBaseline
    b = AUBaseline(seconds=1.0, min_samples=5, cap=0.3)
    for i in range(10):
        b.update({"AU4": 0.2, "AU7": 0.6}, i * 0.2)
    assert b.calibrated and b.fresh
    assert b.baseline["AU4"] == pytest.approx(0.2) and b.baseline["AU7"] == pytest.approx(0.3)  # capped
    adj = b.adjust({"AU4": 0.2, "AU7": 0.9})
    assert adj["AU4"] == pytest.approx(0.0) and adj["AU7"] == pytest.approx((0.9 - 0.3) / 0.7)


def test_pipeline_calibrates_then_reports_capture_quality_and_painad():
    p = SessionPipeline()
    t0 = 1_700_000_000_000
    r = None
    for b in range(10):
        r = p.process_batch({"samples": [sample(t0 + (b * 5 + i) * 100, {}) for i in range(5)]})
    assert r.calibration["state"] == "calibrating" or r.calibration["progress"] > 0
    assert r.quality["lighting"] == "ok" and r.quality["face_size"] == "ok"
    assert r.painad["items"]["facial_expression"] == 0
    assert r.painad["requires_caregiver"] == ["body_language", "consolability"]
    dark = sample(t0 + 10_000, {}, rgb=[10.0, 10.0, 10.0])
    assert p.process_batch({"samples": [dark]}).quality["lighting"] == "dark"


def test_pipeline_suppresses_facial_alerts_while_calibrating(monkeypatch):
    from src.care_monitor.config import settings
    monkeypatch.setattr(settings, "baseline_seconds", 20.0)
    monkeypatch.setattr(settings, "baseline_min_samples", 40)
    p = SessionPipeline()  # no stored baseline
    t0 = 1_700_000_000_000
    alerts = []
    for b in range(4):
        alerts += p.process_batch({"samples": [sample(t0 + (b * 5 + i) * 100, PAIN) for i in range(5)]}).alerts
    assert not [a for a in alerts if "pain" in a["key"]]
    assert p.take_new_baseline() is None or p.baseline.calibrated


def test_live_alert_config_update():
    p = SessionPipeline(baseline={})
    p.apply_alert_config({"muted": ["severe_pain", "moderate_pain"], "hr_high": 110})
    assert p.rppg.hr_high == 110 and p.alerts.config.muted == ("severe_pain", "moderate_pain")
    t0 = 1_700_000_000_000
    alerts = []
    for b in range(4):
        alerts += p.process_batch({"samples": [sample(t0 + (b * 5 + i) * 100, PAIN) for i in range(5)]}).alerts
    assert not [a for a in alerts if a["key"] == "severe_pain"]


def test_painad_scoring_rules():
    from src.care_monitor.inference.painad import VocalisationTracker, interpret, score_breathing, score_facial
    assert score_facial("severe", {}) == 2 and score_facial("none", {"AU4": 0.5}) == 1 and score_facial("none", {}) == 0
    assert score_breathing(16, "good") == 0 and score_breathing(27, "good") == 1 and score_breathing(34, "fair") == 2
    assert score_breathing(16, "poor") is None
    v = VocalisationTracker()
    assert v.score(0) is None
    v.add("calm", 0)
    assert v.score(1) == 0
    v.add("moaning", 2)
    assert v.score(3) == 1
    v.add("crying", 4)
    assert v.score(5) == 2
    assert [interpret(x) for x in (0, 2, 5, 8)] == ["no_pain_behaviours", "mild", "moderate", "severe"]


def test_rppg_needs_enough_data():
    est = RPPGEstimator()
    for i in range(20):
        est.add_sample((1, 2, 3), i * 0.1)
    assert est.estimate().signal_quality == "no_signal"


# ---------------------------------------------------------------- voice
def test_voice_features_detect_pitch_of_tone():
    sr = 16000
    tt = np.arange(sr) / sr
    f = extract_features(0.5 * np.sin(2 * np.pi * 200 * tt), sr)
    assert 180 < f.pitch_mean < 220
    assert f.is_voiced


def test_voice_silence():
    assert analyze(np.zeros(16000)).vocal_state == VocalState.SILENT


def test_voice_feature_mapping_sanitises():
    f = VoiceFeatures.from_mapping({"pitch_mean": "bad", "energy_mean": 9, "spectral_centroid": float("nan")})
    assert f.pitch_mean == 0 and f.energy_mean == 1 and f.spectral_centroid == 0
    assert classify(f).vocal_state == VocalState.SILENT
