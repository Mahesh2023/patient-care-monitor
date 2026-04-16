"""
Unit tests for Pain Detector module.
"""

import pytest
import numpy as np

from modules.pain_detector import PainDetector, PainLevel, PainAssessment
from modules.face_analyzer import AUEstimates


def test_pain_detector_initialization():
    """Test that PainDetector initializes correctly."""
    detector = PainDetector()
    assert detector.mild_threshold == 1.5
    assert detector.moderate_threshold == 4.0
    assert detector.severe_threshold == 8.0
    assert len(detector._score_history) == 0


def test_compute_pspi():
    """Test PSPI computation formula."""
    detector = PainDetector()
    
    # Test case: no pain
    aus = AUEstimates(AU4=0.0, AU6=0.0, AU7=0.0, AU9=0.0, AU10=0.0, AU43=0.0)
    pspi = detector.compute_pspi(aus)
    assert pspi == 0.0
    
    # Test case: moderate pain
    aus = AUEstimates(AU4=0.4, AU6=0.3, AU7=0.2, AU9=0.3, AU10=0.2, AU43=0.2)
    pspi = detector.compute_pspi(aus)
    assert 0 < pspi < 16.0
    
    # Test case: severe pain
    aus = AUEstimates(AU4=0.8, AU6=0.7, AU7=0.6, AU9=0.7, AU10=0.6, AU43=0.8)
    pspi = detector.compute_pspi(aus)
    assert pspi > 5.0


def test_classify_pain():
    """Test pain level classification."""
    detector = PainDetector()
    
    assert detector.classify_pain(0.0) == PainLevel.NONE
    assert detector.classify_pain(2.0) == PainLevel.MILD
    assert detector.classify_pain(5.0) == PainLevel.MODERATE
    assert detector.classify_pain(10.0) == PainLevel.SEVERE


def test_pain_assessment():
    """Test full pain assessment."""
    detector = PainDetector()
    
    aus = AUEstimates(AU4=0.4, AU6=0.3, AU7=0.2, AU9=0.3, AU10=0.2, AU43=0.2)
    assessment = detector.assess(aus, timestamp=0.0)
    
    assert isinstance(assessment, PainAssessment)
    assert assessment.pspi_score >= 0.0
    assert assessment.pain_level in PainLevel
    assert 0.0 <= assessment.confidence <= 1.0
    assert assessment.contributing_aus is not None


def test_pain_assessment_none():
    """Test pain assessment with None input."""
    detector = PainDetector()
    assessment = detector.assess(None, timestamp=0.0)
    
    assert assessment.pspi_score == 0.0
    assert assessment.pain_level == PainLevel.NONE
    assert assessment.confidence == 0.0


def test_get_trend():
    """Test pain trend detection."""
    detector = PainDetector()
    
    # Add some scores
    for _ in range(10):
        aus = AUEstimates(AU4=0.2, AU6=0.1, AU7=0.1, AU9=0.1, AU10=0.1, AU43=0.1)
        detector.assess(aus)
    
    trend = detector.get_trend()
    assert trend in ["increasing", "decreasing", "stable", "insufficient_data"]


def test_reset():
    """Test reset functionality."""
    detector = PainDetector()
    
    aus = AUEstimates(AU4=0.2, AU6=0.1, AU7=0.1, AU9=0.1, AU10=0.1, AU43=0.1)
    detector.assess(aus)
    assert len(detector._score_history) > 0
    
    detector.reset()
    assert len(detector._score_history) == 0


def test_custom_thresholds():
    """Test custom threshold configuration."""
    detector = PainDetector(mild_threshold=2.0, moderate_threshold=5.0, severe_threshold=10.0)
    
    assert detector.mild_threshold == 2.0
    assert detector.moderate_threshold == 5.0
    assert detector.severe_threshold == 10.0
    
    assert detector.classify_pain(1.5) == PainLevel.NONE
    assert detector.classify_pain(3.0) == PainLevel.MILD
    assert detector.classify_pain(7.0) == PainLevel.MODERATE
    assert detector.classify_pain(12.0) == PainLevel.SEVERE
