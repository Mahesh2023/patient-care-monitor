"""PAINAD-aligned observation scoring.

PAINAD (Pain Assessment IN Advanced Dementia; Warden, Hurley & Volicer,
JAMDA 2003) scores five behaviours 0-2 each (total 0-10): breathing,
negative vocalisation, facial expression, body language, consolability.
Commonly used bands: 1-3 mild, 4-6 moderate, 7-10 severe — though the
score "indicates whether the person might be experiencing pain" rather than
an exact severity, and must be combined with knowledge of the person.

The system can *suggest* three items from sensors; body language and
consolability require a caregiver (camera framing is face-only and
consolability needs interaction). Suggested items are never presented as a
completed PAINAD — a caregiver confirms/overrides and records the assessment.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass

ITEMS = ("breathing", "negative_vocalization", "facial_expression", "body_language", "consolability")
AUTO_ITEMS = ITEMS[:3]


def interpret(total: int) -> str:
    if total <= 0:
        return "no_pain_behaviours"
    if total <= 3:
        return "mild"
    if total <= 6:
        return "moderate"
    return "severe"


def score_facial(pain_level: str, aus: dict[str, float], on: float = 0.15) -> int:
    """0 smiling/inexpressive · 1 sad, frightened, frown · 2 facial grimace."""
    if pain_level in ("moderate", "severe"):
        return 2
    if aus.get("AU4", 0) > on or aus.get("AU15", 0) > on or aus.get("AU1", 0) > on + 0.15:
        return 1
    return 0


def score_breathing(brpm: float, quality: str) -> int | None:
    """0 normal · 1 occasional laboured / short hyperventilation · 2 noisy laboured / long hyperventilation."""
    if quality not in ("good", "fair") or brpm <= 0:
        return None
    if brpm > 30 or brpm < 8:
        return 2
    if brpm > 24 or brpm < 10:
        return 1
    return 0


@dataclass
class _Voc:
    t: float
    state: str


class VocalisationTracker:
    """Negative vocalisation over a 60 s window: occasional (1) vs repeated / crying (2)."""

    NEG = ("moaning", "distressed", "crying")

    def __init__(self, window_s: float = 60.0) -> None:
        self.window_s = window_s
        self._ev: deque[_Voc] = deque(maxlen=120)
        self.has_audio = False

    def add(self, state: str, t: float) -> None:
        self.has_audio = True
        self._ev.append(_Voc(t, state))

    def score(self, now: float) -> int | None:
        if not self.has_audio:
            return None
        recent = [e for e in self._ev if now - e.t <= self.window_s and e.state in self.NEG]
        if any(e.state == "crying" for e in recent) or len(recent) >= 3:
            return 2
        return 1 if recent else 0


def auto_items(pain_level: str, aus: dict[str, float], brpm: float, rr_quality: str,
               vocal: int | None) -> dict:
    items = {
        "breathing": score_breathing(brpm, rr_quality),
        "negative_vocalization": vocal,
        "facial_expression": score_facial(pain_level, aus),
    }
    scored = [v for v in items.values() if v is not None]
    return {
        "items": items,
        "auto_total": int(sum(scored)),
        "auto_items_scored": len(scored),
        "requires_caregiver": ["body_language", "consolability"],
    }
