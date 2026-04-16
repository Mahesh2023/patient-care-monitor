"""
Unit tests for Fusion Engine module.
"""

import pytest

from modules.fusion_engine import FusionEngine, PatientState, PatientAlertLevel
from modules.face_analyzer import FaceAnalysisResult, AUEstimates
from modules.pain_detector import PainAssessment, PainLevel
from modules.voice_analyzer import VoiceAnalysisResult, VocalState
from modules.rppg_estimator import HeartRateResult
from modules.text_sentiment import SentimentResult
import numpy as np


def test_fusion_engine_initialization():
    """Test that FusionEngine initializes correctly."""
    engine = FusionEngine()
    assert len(engine._state_history) == 0
    assert engine._alert_cooldown == 30.0
    assert engine._consecutive_alert_frames == 0


def test_fuse_with_no_data():
    """Test fusion with no input data."""
    engine = FusionEngine()
    state = engine.fuse(timestamp=0.0)
    
    assert isinstance(state, PatientState)
    assert state.comfort_level == 0.5
    assert state.arousal_level == 0.5
    assert state.pain_level == 0.0
    assert state.alert_level == PatientAlertLevel.NORMAL


def test_fuse_with_face_data():
    """Test fusion with face analysis data."""
    engine = FusionEngine()
    
    face_result = FaceAnalysisResult(
        face_detected=True,
        aus=AUEstimates(AU12=0.5, AU4=0.1),
        timestamp=0.0
    )
    
    state = engine.fuse(face_result=face_result, timestamp=0.0)
    
    assert state.face_detected == True
    # AU12 (smile) should increase comfort
    assert state.comfort_level > 0.5


def test_fuse_with_pain_data():
    """Test fusion with pain assessment data."""
    engine = FusionEngine()
    
    pain_assessment = PainAssessment(
        pspi_score=6.0,
        pain_level=PainLevel.MODERATE,
        confidence=0.7,
        timestamp=0.0
    )
    
    state = engine.fuse(pain_assessment=pain_assessment, timestamp=0.0)
    
    assert state.pain_level == 0.6  # 6.0 / 10.0
    assert state.alert_level == PatientAlertLevel.CONCERN
    assert len(state.alert_reasons) > 0


def test_fuse_with_severe_pain():
    """Test fusion with severe pain triggers urgent alert."""
    engine = FusionEngine()
    
    pain_assessment = PainAssessment(
        pspi_score=10.0,
        pain_level=PainLevel.SEVERE,
        confidence=0.8,
        timestamp=0.0
    )
    
    state = engine.fuse(pain_assessment=pain_assessment, timestamp=0.0)
    
    assert state.alert_level == PatientAlertLevel.URGENT


def test_fuse_with_voice_distress():
    """Test fusion with voice distress data."""
    engine = FusionEngine()
    
    voice_result = VoiceAnalysisResult(
        vocal_state=VocalState.DISTRESSED,
        arousal=0.8,
        valence=0.2,
        confidence=0.7,
        timestamp=0.0
    )
    
    state = engine.fuse(voice_result=voice_result, timestamp=0.0)
    
    assert state.alert_level == PatientAlertLevel.CONCERN
    assert any("vocal distress" in reason.lower() for reason in state.alert_reasons)


def test_fuse_with_heart_rate_abnormal():
    """Test fusion with abnormal heart rate."""
    engine = FusionEngine()
    
    hr_result = HeartRateResult(
        bpm=120.0,
        confidence=0.6,
        signal_quality="good",
        is_abnormal=True,
        abnormality_type="tachycardia",
        timestamp=0.0
    )
    
    state = engine.fuse(heart_rate=hr_result, timestamp=0.0)
    
    assert state.alert_level == PatientAlertLevel.ATTENTION


def test_fuse_multimodal():
    """Test fusion with multiple modalities."""
    engine = FusionEngine()
    
    face_result = FaceAnalysisResult(
        face_detected=True,
        aus=AUEstimates(AU12=0.3, AU4=0.5),
        timestamp=0.0
    )
    
    pain_assessment = PainAssessment(
        pspi_score=3.0,
        pain_level=PainLevel.MODERATE,
        confidence=0.6,
        timestamp=0.0
    )
    
    state = engine.fuse(
        face_result=face_result,
        pain_assessment=pain_assessment,
        timestamp=0.0
    )
    
    assert state.comfort_level < 0.5  # Pain should lower comfort
    assert state.pain_level > 0.0
    assert len(state.observations) > 0


def test_get_state_trend():
    """Test state trend computation."""
    engine = FusionEngine()
    
    # Add some states
    for i in range(10):
        state = PatientState(
            comfort_level=0.5 + i * 0.05,
            pain_level=0.2 - i * 0.01,
            timestamp=float(i)
        )
        engine._state_history.append(state)
    
    trend = engine.get_state_trend()
    assert trend["trend"] in ["improving", "declining", "stable"]
    assert "mean_comfort" in trend
    assert "mean_pain" in trend


def test_get_history():
    """Test getting state history."""
    engine = FusionEngine()
    
    state = PatientState(comfort_level=0.7, timestamp=0.0)
    engine._state_history.append(state)
    
    history = engine.get_history()
    assert len(history) == 1
    assert history[0]["comfort_level"] == 0.7


def test_engagement_detection():
    """Test engagement level detection."""
    engine = FusionEngine()
    
    # Face detected, eyes open
    face_result = FaceAnalysisResult(
        face_detected=True,
        aus=AUEstimates(AU43=0.1),  # Eyes open
        timestamp=0.0
    )
    state = engine.fuse(face_result=face_result, timestamp=0.0)
    assert state.engagement_level >= 0.6
    
    # No face detected
    face_result = FaceAnalysisResult(face_detected=False, timestamp=0.0)
    state = engine.fuse(face_result=face_result, timestamp=0.0)
    assert state.engagement_level < 0.5


def test_high_arousal_low_comfort_alert():
    """Test alert trigger for high arousal + low comfort."""
    engine = FusionEngine()
    
    face_result = FaceAnalysisResult(
        face_detected=True,
        aus=AUEstimates(AU4=0.8, AU5=0.8, AU26=0.8),  # High arousal indicators
        timestamp=0.0
    )
    
    pain_assessment = PainAssessment(
        pspi_score=8.0,
        pain_level=PainLevel.SEVERE,
        confidence=0.7,
        timestamp=0.0
    )
    
    state = engine.fuse(
        face_result=face_result,
        pain_assessment=pain_assessment,
        timestamp=0.0
    )
    
    # Should trigger concern due to high arousal + low comfort
    assert state.alert_level in [PatientAlertLevel.CONCERN, PatientAlertLevel.URGENT]
