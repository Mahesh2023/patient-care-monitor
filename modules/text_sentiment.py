"""
Text Sentiment Module
=====================
Analyzes text input (caregiver notes, patient speech-to-text) for sentiment.

Uses a simple lexicon-based approach for transparency and no external API dependency.
This is intentionally rule-based rather than ML-based to maintain:
1. Full transparency in how scores are computed
2. No data leaving the local machine (privacy)
3. Deterministic, explainable outputs

For production use, consider integrating a local LLM or BERT model.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional
import re


@dataclass
class SentimentResult:
    """Text sentiment analysis result."""
    text: str = ""
    valence: float = 0.5       # 0 = very negative, 1 = very positive
    arousal: float = 0.5       # 0 = very calm, 1 = very agitated
    pain_mentioned: bool = False
    distress_mentioned: bool = False
    key_terms: List[str] = None
    confidence: float = 0.0
    timestamp: float = 0.0

    def __post_init__(self):
        if self.key_terms is None:
            self.key_terms = []


class TextSentimentAnalyzer:
    """
    Lexicon-based text sentiment analyzer for patient care context.
    Focused on pain, distress, comfort, and wellbeing vocabulary.
    """

    # Domain-specific lexicons
    PAIN_TERMS = {
        "pain": -0.8, "hurts": -0.8, "hurt": -0.7, "ache": -0.6,
        "aching": -0.6, "sore": -0.5, "burning": -0.7, "sharp": -0.6,
        "throbbing": -0.7, "stabbing": -0.8, "cramping": -0.6,
        "stinging": -0.5, "tender": -0.4, "agony": -0.9, "excruciating": -0.9,
        "uncomfortable": -0.4, "discomfort": -0.4,
    }

    DISTRESS_TERMS = {
        "help": -0.5, "scared": -0.7, "afraid": -0.7, "anxious": -0.6,
        "worried": -0.5, "confused": -0.5, "dizzy": -0.5, "nauseous": -0.6,
        "sick": -0.5, "weak": -0.4, "tired": -0.3, "exhausted": -0.5,
        "can't breathe": -0.9, "choking": -0.9, "falling": -0.7,
        "lonely": -0.5, "alone": -0.4, "cold": -0.3, "hot": -0.3,
        "crying": -0.6, "please": -0.3, "stop": -0.4,
    }

    COMFORT_TERMS = {
        "better": 0.5, "good": 0.5, "fine": 0.3, "okay": 0.2,
        "comfortable": 0.6, "relaxed": 0.6, "calm": 0.5,
        "happy": 0.7, "grateful": 0.6, "thank": 0.4, "thanks": 0.4,
        "nice": 0.4, "warm": 0.3, "safe": 0.5, "peaceful": 0.6,
        "sleeping": 0.3, "resting": 0.3, "eating": 0.2, "hungry": -0.2,
    }

    INTENSITY_MODIFIERS = {
        "very": 1.5, "really": 1.4, "extremely": 1.8, "terribly": 1.6,
        "slightly": 0.5, "a little": 0.6, "somewhat": 0.7,
        "much": 1.3, "so": 1.3, "too": 1.3, "quite": 1.2,
    }

    NEGATORS = {"not", "no", "don't", "doesn't", "didn't", "never", "neither", "nor", "can't", "won't"}

    def __init__(self):
        self._history: List[SentimentResult] = []

    def analyze(self, text: str, timestamp: float = 0.0) -> SentimentResult:
        """Analyze text for sentiment in patient care context."""
        if not text or not text.strip():
            return SentimentResult(timestamp=timestamp)

        text_lower = text.lower().strip()
        words = re.findall(r'\b\w+\b', text_lower)

        scores = []
        key_terms = []
        pain_mentioned = False
        distress_mentioned = False

        # Check for multi-word expressions first
        for term, score in {**self.DISTRESS_TERMS}.items():
            if " " in term and term in text_lower:
                scores.append(score)
                key_terms.append(term)
                if term in self.DISTRESS_TERMS:
                    distress_mentioned = True

        # Process individual words with context
        for i, word in enumerate(words):
            score = None
            source = None

            if word in self.PAIN_TERMS:
                score = self.PAIN_TERMS[word]
                source = "pain"
                pain_mentioned = True
            elif word in self.DISTRESS_TERMS:
                score = self.DISTRESS_TERMS[word]
                source = "distress"
                distress_mentioned = True
            elif word in self.COMFORT_TERMS:
                score = self.COMFORT_TERMS[word]
                source = "comfort"

            if score is not None:
                # Check for negation in preceding 3 words
                preceding = words[max(0, i - 3):i]
                if any(w in self.NEGATORS for w in preceding):
                    score = -score * 0.5  # Negate but weaken

                # Check for intensity modifiers
                if i > 0 and words[i - 1] in self.INTENSITY_MODIFIERS:
                    score *= self.INTENSITY_MODIFIERS[words[i - 1]]

                scores.append(score)
                key_terms.append(word)

        # Compute final valence
        if scores:
            raw_valence = np.clip(np.mean(scores), -1, 1)
            valence = (raw_valence + 1) / 2.0  # Map [-1,1] to [0,1]
            # Arousal from absolute values
            arousal = np.clip(np.mean([abs(s) for s in scores]), 0, 1)
            confidence = min(0.9, 0.3 + len(scores) * 0.1)
        else:
            valence = 0.5
            arousal = 0.3
            confidence = 0.1

        result = SentimentResult(
            text=text,
            valence=round(float(valence), 2),
            arousal=round(float(arousal), 2),
            pain_mentioned=pain_mentioned,
            distress_mentioned=distress_mentioned,
            key_terms=key_terms,
            confidence=round(float(confidence), 2),
            timestamp=timestamp,
        )

        self._history.append(result)
        return result

    def get_recent_summary(self, n: int = 5) -> dict:
        """Summarize recent text analyses."""
        recent = self._history[-n:]
        if not recent:
            return {"status": "no_data"}

        return {
            "mean_valence": round(float(np.mean([r.valence for r in recent])), 2),
            "mean_arousal": round(float(np.mean([r.arousal for r in recent])), 2),
            "pain_mentioned_count": sum(1 for r in recent if r.pain_mentioned),
            "distress_mentioned_count": sum(1 for r in recent if r.distress_mentioned),
            "total_entries": len(recent),
        }

    def reset(self):
        self._history.clear()


# Need numpy for the lexicon approach
import numpy as np
