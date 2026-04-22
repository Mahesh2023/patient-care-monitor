"""Dimensional distress state inference from AUs + head + gaze + blink + HR + PSPI.

Design decision — **no discrete "emotion labels"**:
  Following Barrett et al. (2019, PSPI 20(1)) — "Emotional Expressions
  Reconsidered" — we do NOT assign outputs like "angry" or "sad" from a
  single facial configuration. Instead we report four continuous clinical
  dimensions that are directly actionable for caregivers:

    comfort    in [0,1]  — low = apparently uncomfortable
    arousal    in [0,1]  — low = unresponsive; high = agitated
    pain       in [0,1]  — normalised PSPI
    engagement in [0,1]  — "is the patient responsive?"

Each dimension is computed by a transparent, auditable rule from the
multimodal features. This is what clinical audit committees can review.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Tuple

from ..features.pain import PainAssessment, PainLevel


@dataclass
class DistressState:
    comfort: float = 0.5
    arousal: float = 0.5
    pain: float = 0.0
    engagement: float = 0.5
    # Behavioural observations (strings — inspectable by caregivers)
    observations: List[str] = field(default_factory=list)
    # Qualitative cognitive tag (for dashboard chips, never "true emotion")
    behavioural_tag: str = "neutral"
    confidence: float = 0.0
    timestamp: float = 0.0


# Thresholds (tuned conservatively for clinical use — err on the side
# of "don't miss distress" rather than false-alarm suppression).
_AU_ON = 0.15


def _on(aus: Dict[str, float], key: str) -> bool:
    return float(aus.get(key, 0.0)) > _AU_ON


def _behavioural_tag(aus: Dict[str, float], head_pose: Dict[str, float],
                     gaze: Dict[str, float], blink_rpm: float,
                     pain_level: PainLevel) -> Tuple[str, float]:
    """Return (tag, confidence) — rule-based, most-specific-first.

    Tags are *behavioural*, not emotional. A tag of 'grimace_pattern' does
    NOT claim the patient is 'in pain' — only that the facial configuration
    matches the well-documented pain-expression pattern.
    """
    roll = float(head_pose.get("roll", 0.0))
    averted = bool(gaze.get("averted", False))
    total_au = float(sum(aus.values()))

    if pain_level == PainLevel.SEVERE:
        return "grimace_pattern_severe", 0.85
    if pain_level == PainLevel.MODERATE:
        return "grimace_pattern_moderate", 0.7
    if _on(aus, "AU4") and _on(aus, "AU7") and abs(roll) > 10:
        return "furrowed_concentrating_or_confused", 0.65
    if _on(aus, "AU4") and 0 < blink_rpm < 10:
        return "high_cognitive_load_or_fatigue", 0.6
    if blink_rpm > 25 and _on(aus, "AU4"):
        return "agitation_pattern", 0.65
    if total_au < 1.0 and blink_rpm < 8 and averted:
        return "withdrawn_or_disengaged", 0.6
    if _on(aus, "AU6") and _on(aus, "AU12"):
        return "duchenne_smile_pattern", 0.7
    if _on(aus, "AU12") and not _on(aus, "AU6"):
        return "social_smile_pattern", 0.55
    if not averted and total_au > 0.3:
        return "engaged_expressive", 0.55
    if averted:
        return "gaze_averted", 0.5
    return "neutral", 0.4


def infer_distress(
    aus: Dict[str, float],
    head_pose: Dict[str, float],
    gaze: Dict[str, float],
    blink_rpm: float,
    pain: PainAssessment,
    heart_rate_bpm: float = 0.0,
    timestamp: float = 0.0,
) -> DistressState:
    obs: List[str] = []

    # Pain (0-16 PSPI -> [0,1])
    pain_norm = float(min(1.0, max(0.0, pain.pspi / 16.0)))

    # Arousal heuristic: high AU-total OR high blink rate OR high HR
    arousal = 0.5
    if blink_rpm > 25:
        arousal += 0.2; obs.append(f"elevated_blink_rate ({blink_rpm:.0f}/min)")
    elif blink_rpm > 0 and blink_rpm < 8:
        arousal -= 0.15; obs.append(f"slow_blink_rate ({blink_rpm:.0f}/min)")
    if heart_rate_bpm > 100:
        arousal += 0.15; obs.append(f"tachycardia ({heart_rate_bpm:.0f} bpm)")
    elif 0 < heart_rate_bpm < 60:
        arousal -= 0.1; obs.append(f"bradycardia ({heart_rate_bpm:.0f} bpm)")
    au_total = float(sum(aus.values()))
    if au_total > 2.0:
        arousal += 0.1
    arousal = float(max(0.0, min(1.0, arousal + pain_norm * 0.3)))

    # Comfort: inverse of pain, minus negative-affect AUs, plus Duchenne-smile bonus
    comfort = 1.0 - pain_norm
    if _on(aus, "AU4"):
        comfort -= 0.1; obs.append("brow_furrow (AU4)")
    if _on(aus, "AU15"):
        comfort -= 0.1; obs.append("lip_corner_depressor (AU15)")
    if _on(aus, "AU20"):
        comfort -= 0.1; obs.append("lip_stretch (AU20)")
    if _on(aus, "AU6") and _on(aus, "AU12"):
        comfort += 0.1; obs.append("duchenne_smile (AU6+AU12)")
    comfort = float(max(0.0, min(1.0, comfort)))

    # Engagement: head stable + not averted + eyes open
    engagement = 0.5
    if abs(head_pose.get("yaw", 0)) < 20 and abs(head_pose.get("pitch", 0)) < 15:
        engagement += 0.15
    if not gaze.get("averted", False):
        engagement += 0.2
    else:
        obs.append("gaze_averted")
    if aus.get("AU43", 0.0) > 0.5:
        engagement -= 0.3; obs.append("eyes_closed (AU43)")
    engagement = float(max(0.0, min(1.0, engagement)))

    tag, tag_conf = _behavioural_tag(aus, head_pose, gaze, blink_rpm, pain.level)

    # Confidence in the overall snapshot:
    # - high PSPI confidence contributes,
    # - at least one AU active contributes,
    # - heart rate confidence (if we had it) would contribute.
    conf = 0.4 + 0.4 * pain.confidence + (0.2 if au_total > 0.3 else 0.0)
    conf = float(max(0.0, min(1.0, conf)))

    return DistressState(
        comfort=round(comfort, 3),
        arousal=round(arousal, 3),
        pain=round(pain_norm, 3),
        engagement=round(engagement, 3),
        observations=obs,
        behavioural_tag=tag,
        confidence=round(conf, 3),
        timestamp=timestamp,
    )
