"""
Unit tests for Text Sentiment module.
"""

import pytest

from modules.text_sentiment import TextSentimentAnalyzer, SentimentResult


def test_text_analyzer_initialization():
    """Test that TextSentimentAnalyzer initializes correctly."""
    analyzer = TextSentimentAnalyzer()
    assert len(analyzer._history) == 0


def test_analyze_comfort_text():
    """Test analysis of comfort-related text."""
    analyzer = TextSentimentAnalyzer()
    result = analyzer.analyze("Patient is comfortable and resting well", timestamp=0.0)
    
    assert isinstance(result, SentimentResult)
    assert result.valence > 0.5  # Should be positive
    assert result.pain_mentioned == False
    assert result.distress_mentioned == False


def test_analyze_pain_text():
    """Test analysis of pain-related text."""
    analyzer = TextSentimentAnalyzer()
    result = analyzer.analyze("Patient complaining of sharp pain in lower back", timestamp=0.0)
    
    assert isinstance(result, SentimentResult)
    assert result.valence < 0.5  # Should be negative
    assert result.pain_mentioned == True
    assert "pain" in result.key_terms


def test_analyze_distress_text():
    """Test analysis of distress-related text."""
    analyzer = TextSentimentAnalyzer()
    result = analyzer.analyze("Patient is very anxious and confused, keeps asking for help", timestamp=0.0)
    
    assert isinstance(result, SentimentResult)
    assert result.valence < 0.5  # Should be negative
    assert result.distress_mentioned == True
    assert result.arousal > 0.5  # Should be high arousal


def test_negation_handling():
    """Test negation handling in sentiment analysis."""
    analyzer = TextSentimentAnalyzer()
    
    result = analyzer.analyze("Patient is not in pain", timestamp=0.0)
    # The negation should flip the sentiment somewhat
    assert result.pain_mentioned == True  # "pain" is still detected
    assert result.valence > 0.3  # But valence should be less negative


def test_intensity_modifiers():
    """Test intensity modifiers."""
    analyzer = TextSentimentAnalyzer()
    
    result_mild = analyzer.analyze("Patient has some pain", timestamp=0.0)
    result_severe = analyzer.analyze("Patient has very severe pain", timestamp=0.0)
    
    # "Very severe" should be more negative than "some"
    assert result_severe.valence < result_mild.valence


def test_empty_text():
    """Test handling of empty text."""
    analyzer = TextSentimentAnalyzer()
    result = analyzer.analyze("", timestamp=0.0)
    
    assert result.valence == 0.5
    assert result.arousal == 0.3
    assert result.confidence == 0.0


def test_get_recent_summary():
    """Test getting recent summary."""
    analyzer = TextSentimentAnalyzer()
    
    analyzer.analyze("Patient is comfortable", timestamp=0.0)
    analyzer.analyze("Patient has some pain", timestamp=1.0)
    
    summary = analyzer.get_recent_summary(n=2)
    assert summary["total_entries"] == 2
    assert "mean_valence" in summary
    assert "mean_arousal" in summary


def test_reset():
    """Test reset functionality."""
    analyzer = TextSentimentAnalyzer()
    
    analyzer.analyze("Test text", timestamp=0.0)
    assert len(analyzer._history) > 0
    
    analyzer.reset()
    assert len(analyzer._history) == 0


def test_multi_word_expressions():
    """Test multi-word expressions like 'can't breathe'."""
    analyzer = TextSentimentAnalyzer()
    result = analyzer.analyze("Patient says they can't breathe", timestamp=0.0)
    
    assert result.distress_mentioned == True
    assert result.valence < 0.5
