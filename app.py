"""
Patient Care Monitor - Gradio Dashboard (Comprehensive Edition)
================================================================
Real-time facial analysis with webcam streaming, pain detection,
and comprehensive clinical-quality monitoring output.

Every metric produced by the analysis pipeline is surfaced in
detailed, organized panels with scientific context.

Deploy: Hugging Face Spaces (Gradio SDK)
"""

import os
import sys
import time
import html as html_module

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import cv2
import numpy as np
import gradio as gr

from modules.face_analyzer import FaceAnalyzer, FaceAnalysisResult, AUEstimates
from modules.pain_detector import PainDetector, PainLevel
from modules.fusion_engine import FusionEngine, PatientAlertLevel
from modules.text_sentiment import TextSentimentAnalyzer

# ─── Global State ────────────────────────────────────────────
face_analyzer = None
pain_detector = PainDetector()
fusion_engine = FusionEngine()
text_analyzer = TextSentimentAnalyzer()


def get_face_analyzer():
    """Lazy-init face analyzer (loads model once)."""
    global face_analyzer
    if face_analyzer is None:
        face_analyzer = FaceAnalyzer()
    return face_analyzer


# ─── AU Metadata (for display) ───────────────────────────────
AU_META = {
    "AU1":  {"name": "Inner Brow Raiser",      "muscle": "Frontalis (medial)",                  "clinical": "Sadness, fear, surprise, worry"},
    "AU2":  {"name": "Outer Brow Raiser",      "muscle": "Frontalis (lateral)",                 "clinical": "Surprise, fear"},
    "AU4":  {"name": "Brow Lowerer",           "muscle": "Corrugator supercilii",               "clinical": "PAIN, anger, concentration, distress"},
    "AU5":  {"name": "Upper Lid Raiser",       "muscle": "Levator palpebrae superioris",        "clinical": "Fear, surprise, attention"},
    "AU6":  {"name": "Cheek Raiser",           "muscle": "Orbicularis oculi (orbital)",          "clinical": "Genuine smile (Duchenne), PAIN"},
    "AU7":  {"name": "Lid Tightener",          "muscle": "Orbicularis oculi (palpebral)",        "clinical": "PAIN, squinting, effort"},
    "AU9":  {"name": "Nose Wrinkler",          "muscle": "Levator labii sup. alaeque nasi",      "clinical": "Disgust, PAIN"},
    "AU10": {"name": "Upper Lip Raiser",       "muscle": "Levator labii superioris",             "clinical": "Disgust, PAIN"},
    "AU12": {"name": "Lip Corner Puller",      "muscle": "Zygomaticus major",                    "clinical": "Smile indicator"},
    "AU15": {"name": "Lip Corner Depressor",   "muscle": "Depressor anguli oris",                "clinical": "Sadness, disappointment"},
    "AU17": {"name": "Chin Raiser",            "muscle": "Mentalis",                             "clinical": "Doubt, displeasure, pouting"},
    "AU20": {"name": "Lip Stretcher",          "muscle": "Risorius / Platysma",                  "clinical": "Fear, tension"},
    "AU23": {"name": "Lip Tightener",          "muscle": "Orbicularis oris",                     "clinical": "Anger, determination"},
    "AU25": {"name": "Lips Part",              "muscle": "Orbicularis oris relaxation",           "clinical": "Speech, surprise, relaxation"},
    "AU26": {"name": "Jaw Drop",              "muscle": "Masseter / internal pterygoid relax",   "clinical": "Surprise, yawning, speech"},
    "AU43": {"name": "Eyes Closed",           "muscle": "Levator palpebrae relaxation",          "clinical": "PAIN, drowsiness, sleep, blink"},
    "AU45": {"name": "Blink",                 "muscle": "Orbicularis oculi",                     "clinical": "Reflex, fatigue indicator"},
}

PAIN_AUS = {"AU4", "AU6", "AU7", "AU9", "AU10", "AU43"}


# ─── HTML Rendering Helpers ──────────────────────────────────

def _bar_html(value, max_val=1.0, color="#4dabf7", label="", width_px=180, show_pct=True):
    """Render a horizontal progress bar as inline HTML."""
    pct = min(value / max_val, 1.0) * 100 if max_val > 0 else 0
    pct_text = f"{pct:.0f}%" if show_pct else f"{value:.3f}"
    return (
        f'<div style="display:flex;align-items:center;gap:6px;margin:2px 0;">'
        f'<span style="min-width:140px;font-size:0.78em;color:#94a3b8;text-align:right;">{label}</span>'
        f'<div style="width:{width_px}px;height:14px;background:#1e293b;border-radius:3px;overflow:hidden;">'
        f'<div style="width:{pct:.1f}%;height:100%;background:{color};border-radius:3px;transition:width 0.2s;"></div>'
        f'</div>'
        f'<span style="min-width:44px;font-size:0.75em;color:#cbd5e1;">{pct_text}</span>'
        f'</div>'
    )


def _section_header(title, icon=""):
    """Section header with optional icon."""
    return (
        f'<div style="margin:12px 0 6px;padding:4px 8px;background:#1e293b;'
        f'border-left:3px solid #4dabf7;border-radius:0 4px 4px 0;">'
        f'<strong style="color:#e2e8f0;font-size:0.88em;">{icon} {title}</strong>'
        f'</div>'
    )


def _kv(key, value, color="#e2e8f0"):
    """Key-value line."""
    return (
        f'<div style="display:flex;gap:8px;margin:1px 0;padding:1px 8px;">'
        f'<span style="color:#64748b;font-size:0.78em;min-width:150px;">{key}</span>'
        f'<span style="color:{color};font-size:0.82em;font-weight:600;">{value}</span>'
        f'</div>'
    )


def _badge(text, bg="#334155", fg="#e2e8f0"):
    """Small inline badge."""
    return (
        f'<span style="display:inline-block;padding:2px 8px;background:{bg};'
        f'color:{fg};border-radius:10px;font-size:0.72em;font-weight:600;margin:0 2px;">'
        f'{text}</span>'
    )


def _intensity_color(val):
    """Color from green (0) to red (1) for AU intensity."""
    if val < 0.15:
        return "#475569"   # dim gray (inactive)
    if val < 0.3:
        return "#22c55e"   # green (trace)
    if val < 0.5:
        return "#eab308"   # yellow (mild)
    if val < 0.7:
        return "#f97316"   # orange (moderate)
    return "#ef4444"       # red (strong)


def _pain_color(pspi):
    """Color for pain score."""
    if pspi < 1.5:
        return "#22c55e"
    if pspi < 4.0:
        return "#eab308"
    if pspi < 8.0:
        return "#f97316"
    return "#ef4444"


def _alert_style(level):
    """Background/foreground for alert level badge."""
    styles = {
        PatientAlertLevel.NORMAL:    ("#1a3a2a", "#4ade80"),
        PatientAlertLevel.ATTENTION: ("#3a3a1a", "#fbbf24"),
        PatientAlertLevel.CONCERN:   ("#3a2a1a", "#fb923c"),
        PatientAlertLevel.URGENT:    ("#3a1a1a", "#f87171"),
    }
    return styles.get(level, ("#334155", "#e2e8f0"))


# ─── Comprehensive Analysis HTML Builder ─────────────────────

def build_analysis_html(face_result: FaceAnalysisResult,
                        pain_result,
                        fused,
                        pain_trend: str,
                        elapsed_ms: float) -> str:
    """Build the full detailed analysis HTML panel."""
    parts = []

    # Container
    parts.append('<div style="font-family:\'Inter\',system-ui,sans-serif;color:#e2e8f0;'
                 'background:#0f172a;padding:12px;border-radius:8px;max-height:750px;overflow-y:auto;">')

    # ── 1. Status / Summary Bar ──
    alert_bg, alert_fg = _alert_style(fused.alert_level)
    alert_badge = _badge(fused.alert_level.value.upper(), alert_bg, alert_fg)
    face_badge = _badge("FACE DETECTED", "#1a3a2a", "#4ade80") if face_result.face_detected else _badge("NO FACE", "#3a1a1a", "#f87171")
    conf_badge = _badge(f"Confidence: {fused.overall_confidence:.0%}", "#1e293b", "#94a3b8")
    fps_badge = _badge(f"{elapsed_ms:.0f}ms", "#1e293b", "#64748b")

    parts.append(
        f'<div style="display:flex;flex-wrap:wrap;gap:6px;align-items:center;margin-bottom:8px;">'
        f'{face_badge} {alert_badge} {conf_badge} {fps_badge}'
        f'</div>'
    )

    if not face_result.face_detected:
        parts.append('<p style="color:#64748b;padding:20px;text-align:center;">No face detected. Position face in webcam view.</p>')
        parts.append('</div>')
        return "".join(parts)

    # ── 2. Primary Dimensional Metrics ──
    parts.append(_section_header("Dimensional State (Russell Circumplex)", ""))
    metrics = [
        ("Comfort", fused.comfort_level, "#22c55e" if fused.comfort_level > 0.5 else "#f97316"),
        ("Arousal", fused.arousal_level, "#3b82f6" if fused.arousal_level < 0.7 else "#ef4444"),
        ("Pain", fused.pain_level, _pain_color(pain_result.pspi_score)),
        ("Engagement", fused.engagement_level, "#a78bfa"),
    ]
    for name, val, color in metrics:
        parts.append(_bar_html(val, 1.0, color, name, 220, True))

    # ── 3. Head Pose ──
    if face_result.head_pose:
        pitch, yaw, roll = face_result.head_pose
        parts.append(_section_header("Head Pose Estimation (solvePnP)", ""))

        # Interpretation
        pose_notes = []
        if abs(pitch) > 15:
            pose_notes.append("tilted " + ("down" if pitch > 0 else "up"))
        if abs(yaw) > 15:
            pose_notes.append("turned " + ("right" if yaw > 0 else "left"))
        if abs(roll) > 15:
            pose_notes.append("head tilt " + ("right" if roll > 0 else "left"))
        pose_interp = ", ".join(pose_notes) if pose_notes else "facing forward"

        parts.append(_kv("Pitch (up/down)", f"{pitch:+.1f}deg"))
        parts.append(_kv("Yaw (left/right)", f"{yaw:+.1f}deg"))
        parts.append(_kv("Roll (tilt)", f"{roll:+.1f}deg"))
        parts.append(_kv("Interpretation", pose_interp, "#94a3b8"))

    # ── 4. Eye Analysis ──
    parts.append(_section_header("Eye Analysis (Soukupova & Cech, 2016)", ""))
    ear_l = face_result.eye_aspect_ratio_left
    ear_r = face_result.eye_aspect_ratio_right
    ear_avg = (ear_l + ear_r) / 2.0

    # EAR thresholds: ~0.25 normal open, <0.20 drooping, <0.15 closed
    drowsy = ear_avg < 0.20
    eyes_closed = ear_avg < 0.15
    eye_status = "CLOSED" if eyes_closed else ("DROWSY/DROOPING" if drowsy else "Open")
    eye_color = "#ef4444" if eyes_closed else ("#f97316" if drowsy else "#22c55e")

    parts.append(_bar_html(ear_l, 0.45, "#3b82f6", "EAR Left", 180, False))
    parts.append(_bar_html(ear_r, 0.45, "#3b82f6", "EAR Right", 180, False))
    parts.append(_kv("Average EAR", f"{ear_avg:.3f}"))
    parts.append(_kv("Eye State", _badge(eye_status, "#1e293b", eye_color)))
    asymmetry = abs(ear_l - ear_r)
    if asymmetry > 0.05:
        parts.append(_kv("Asymmetry", f"{asymmetry:.3f} (notable)", "#f97316"))

    # Blink (AU45)
    if face_result.aus:
        parts.append(_kv("Blink Intensity (AU45)", f"{face_result.aus.AU45:.3f}"))

    # ── 5. Mouth & Jaw Analysis ──
    parts.append(_section_header("Mouth & Jaw Analysis", ""))
    mar = face_result.mouth_aspect_ratio
    yawn = mar > 0.6
    speaking = 0.15 < mar < 0.5

    mar_status = "YAWNING" if yawn else ("Possibly speaking" if speaking else "Closed/relaxed")
    mar_color = "#f97316" if yawn else ("#3b82f6" if speaking else "#22c55e")

    parts.append(_bar_html(mar, 1.0, mar_color, "MAR (openness)", 180, False))
    parts.append(_kv("Mouth State", _badge(mar_status, "#1e293b", mar_color)))

    if face_result.aus:
        parts.append(_kv("Jaw Drop (AU26)", f"{face_result.aus.AU26:.3f}"))
        parts.append(_kv("Lips Part (AU25)", f"{face_result.aus.AU25:.3f}"))
        parts.append(_kv("Lip Tightener (AU23)", f"{face_result.aus.AU23:.3f}"))

    # ── 6. Brow Analysis ──
    parts.append(_section_header("Brow Analysis", ""))
    bh_l = face_result.brow_height_left
    bh_r = face_result.brow_height_right
    brow_asym = abs(bh_l - bh_r)

    parts.append(_bar_html(bh_l, 0.5, "#a78bfa", "Left Brow Height", 180, False))
    parts.append(_bar_html(bh_r, 0.5, "#a78bfa", "Right Brow Height", 180, False))
    parts.append(_kv("Brow Asymmetry", f"{brow_asym:.3f}" + (" (notable)" if brow_asym > 0.03 else "")))

    if face_result.aus:
        parts.append(_kv("Inner Brow Raise (AU1)", f"{face_result.aus.AU1:.3f}"))
        parts.append(_kv("Outer Brow Raise (AU2)", f"{face_result.aus.AU2:.3f}"))
        parts.append(_kv("Brow Lowerer (AU4)", f"{face_result.aus.AU4:.3f}"))

    # ── 7. Smile Analysis (Duchenne vs Pan-Am) ──
    if face_result.aus:
        parts.append(_section_header("Smile Analysis (Ekman, 1982)", ""))
        au12 = face_result.aus.AU12
        au6 = face_result.aus.AU6

        if au12 > 0.25:
            if au6 > 0.2:
                smile_type = "Duchenne (genuine)"
                smile_note = "AU6 (cheek raiser) + AU12 (lip corner puller) = crow's feet wrinkles present"
                smile_color = "#22c55e"
            else:
                smile_type = "Pan-Am (social/polite)"
                smile_note = "AU12 present but AU6 absent = no crow's feet engagement"
                smile_color = "#eab308"
        elif au12 > 0.1:
            smile_type = "Trace smile"
            smile_note = "Slight lip corner pull detected"
            smile_color = "#64748b"
        else:
            smile_type = "No smile"
            smile_note = "AU12 < 0.1"
            smile_color = "#475569"

        parts.append(_kv("Smile Type", _badge(smile_type, "#1e293b", smile_color)))
        parts.append(_kv("AU12 (Lip Corner Pull)", f"{au12:.3f}"))
        parts.append(_kv("AU6 (Cheek Raiser)", f"{au6:.3f}"))
        parts.append(f'<div style="padding:2px 8px;font-size:0.72em;color:#64748b;">{smile_note}</div>')

    # ── 8. Action Units (all 17, full FACS detail) ──
    if face_result.aus:
        parts.append(_section_header("Action Units - FACS (Ekman & Friesen, 1978)", ""))
        parts.append(
            '<div style="font-size:0.68em;color:#475569;padding:0 8px;margin-bottom:4px;">'
            'Intensity scale: 0.0 (absent) to 1.0 (max). Pain-relevant AUs marked with *'
            '</div>'
        )

        au_dict = face_result.aus.to_dict()
        for au_key in ["AU1", "AU2", "AU4", "AU5", "AU6", "AU7", "AU9", "AU10",
                        "AU12", "AU15", "AU17", "AU20", "AU23", "AU25", "AU26", "AU43", "AU45"]:
            val = au_dict.get(au_key, 0.0)
            meta = AU_META.get(au_key, {})
            au_name = meta.get("name", "")
            muscle = meta.get("muscle", "")
            is_pain = au_key in PAIN_AUS
            color = _intensity_color(val)

            label = f"{'*' if is_pain else ''}{au_key} {au_name}"

            parts.append(
                f'<div style="display:flex;align-items:center;gap:4px;margin:1px 0;padding:0 4px;">'
                f'<span style="min-width:200px;font-size:0.72em;color:{"#f97316" if is_pain and val > 0.15 else "#94a3b8"};'
                f'text-align:right;">{html_module.escape(label)}</span>'
                f'<div style="width:150px;height:12px;background:#1e293b;border-radius:2px;overflow:hidden;">'
                f'<div style="width:{min(val, 1.0)*100:.1f}%;height:100%;background:{color};'
                f'border-radius:2px;transition:width 0.15s;"></div></div>'
                f'<span style="min-width:38px;font-size:0.7em;color:#cbd5e1;">{val:.3f}</span>'
                f'<span style="font-size:0.62em;color:#475569;">{html_module.escape(muscle)}</span>'
                f'</div>'
            )

    # ── 9. Pain Assessment Breakdown ──
    parts.append(_section_header("Pain Assessment - PSPI (Prkachin & Solomon)", ""))
    pspi = pain_result.pspi_score
    pspi_color = _pain_color(pspi)

    parts.append(
        f'<div style="padding:6px 8px;margin:4px 0;">'
        f'<div style="font-size:1.4em;font-weight:700;color:{pspi_color};">'
        f'PSPI Score: {pspi:.2f} / 16.0</div>'
        f'<div style="font-size:0.75em;color:#64748b;margin-top:2px;">'
        f'Pain Level: {_badge(pain_result.pain_level.value.upper(), "#1e293b", pspi_color)}'
        f'  Confidence: {pain_result.confidence:.0%}'
        f'  Trend: {_badge(pain_trend, "#1e293b", "#94a3b8")}'
        f'</div></div>'
    )

    # PSPI formula breakdown
    parts.append(
        '<div style="padding:2px 8px;font-size:0.72em;color:#64748b;">'
        'PSPI = AU4 + max(AU6, AU7) + max(AU9, AU10) + AU43  (each scaled x5 from 0-1 range)'
        '</div>'
    )

    if pain_result.contributing_aus:
        for au_key, au_val in pain_result.contributing_aus.items():
            parts.append(_bar_html(au_val, 1.0, "#ef4444" if au_val > 0.3 else "#475569",
                                   au_key, 150, False))

    # ── 10. Top Active Blendshapes (raw MediaPipe) ──
    if face_result.blendshapes:
        parts.append(_section_header("MediaPipe Blendshapes (ARKit-compatible, top 20)", ""))
        sorted_bs = sorted(face_result.blendshapes.items(), key=lambda x: -x[1])
        top_bs = [(k, v) for k, v in sorted_bs if v > 0.01][:20]

        if top_bs:
            for bs_name, bs_val in top_bs:
                color = _intensity_color(bs_val)
                parts.append(
                    f'<div style="display:flex;align-items:center;gap:4px;margin:1px 0;padding:0 4px;">'
                    f'<span style="min-width:180px;font-size:0.7em;color:#94a3b8;text-align:right;">'
                    f'{html_module.escape(bs_name)}</span>'
                    f'<div style="width:130px;height:10px;background:#1e293b;border-radius:2px;overflow:hidden;">'
                    f'<div style="width:{min(bs_val, 1.0)*100:.1f}%;height:100%;background:{color};'
                    f'border-radius:2px;"></div></div>'
                    f'<span style="min-width:38px;font-size:0.68em;color:#cbd5e1;">{bs_val:.3f}</span>'
                    f'</div>'
                )
        else:
            parts.append('<div style="padding:4px 8px;font-size:0.75em;color:#475569;">No active blendshapes</div>')

    # ── 11. Behavioral Observations ──
    if fused.observations or fused.alert_reasons:
        parts.append(_section_header("Behavioral Observations", ""))
        if fused.alert_reasons:
            for reason in fused.alert_reasons:
                parts.append(
                    f'<div style="padding:3px 8px;margin:2px 0;background:#3a1a1a;border-radius:4px;'
                    f'font-size:0.78em;color:#f87171;">ALERT: {html_module.escape(reason)}</div>'
                )
        for obs in fused.observations:
            parts.append(
                f'<div style="padding:2px 8px;font-size:0.76em;color:#94a3b8;">'
                f'- {html_module.escape(obs)}</div>'
            )

    # ── 12. Interpretation Note ──
    parts.append(
        '<div style="margin-top:10px;padding:8px;background:#1e293b;border-radius:4px;'
        'border-left:3px solid #f59e0b;font-size:0.68em;color:#94a3b8;">'
        '<strong style="color:#fbbf24;">Interpretation Note:</strong> '
        'Per Barrett et al. (2019, PMID: 31313636), facial action units indicate observable '
        'muscle movements, NOT internal emotional states. AU activations are many-to-many '
        'with emotions. These readings are behavioral observations for caregiver reference, '
        'not diagnoses. PSPI pain detection is validated in Lucey et al. (2011) but individual '
        'variation is significant.'
        '</div>'
    )

    parts.append('</div>')
    return "".join(parts)


# ─── Video Overlay Drawing ───────────────────────────────────

def draw_overlay(img, face_result, pain_result, fused):
    """Draw monitoring HUD on the video frame."""
    h, w = img.shape[:2]
    overlay = img.copy()

    # Semi-transparent top bar
    cv2.rectangle(overlay, (0, 0), (w, 44), (20, 20, 30), -1)
    cv2.addWeighted(overlay, 0.75, img, 0.25, 0, img)

    # Face detection status
    if face_result.face_detected:
        cv2.putText(img, "FACE DETECTED", (12, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.65, (80, 255, 80), 2)
    else:
        cv2.putText(img, "NO FACE DETECTED", (12, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.65, (80, 80, 255), 2)
        return img

    # Pain indicator (right side of top bar)
    pain_color = (80, 255, 80)
    if pain_result.pain_level == PainLevel.MILD:
        pain_color = (80, 255, 255)
    elif pain_result.pain_level == PainLevel.MODERATE:
        pain_color = (80, 165, 255)
    elif pain_result.pain_level == PainLevel.SEVERE:
        pain_color = (80, 80, 255)

    pain_text = f"Pain: {pain_result.pspi_score:.1f} ({pain_result.pain_level.value})"
    cv2.putText(img, pain_text, (w - 320, 30),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, pain_color, 2)

    # Bottom bar -- comfort + arousal
    bar_overlay = img.copy()
    cv2.rectangle(bar_overlay, (0, h - 50), (w, h), (20, 20, 30), -1)
    cv2.addWeighted(bar_overlay, 0.75, img, 0.25, 0, img)

    # Comfort bar
    comfort_pct = fused.comfort_level
    bar_w = int((w // 2 - 30) * comfort_pct)
    cv2.rectangle(img, (12, h - 38), (w // 2 - 18, h - 18), (60, 60, 70), -1)
    bar_color = (80, 200, 80) if comfort_pct > 0.5 else (80, 165, 255)
    cv2.rectangle(img, (12, h - 38), (12 + bar_w, h - 18), bar_color, -1)
    cv2.putText(img, f"Comfort: {int(comfort_pct * 100)}%", (14, h - 42),
                cv2.FONT_HERSHEY_SIMPLEX, 0.45, (200, 200, 220), 1)

    # Arousal bar
    arousal_pct = fused.arousal_level
    a_bar_w = int((w // 2 - 30) * arousal_pct)
    x_start = w // 2 + 6
    cv2.rectangle(img, (x_start, h - 38), (w - 12, h - 18), (60, 60, 70), -1)
    a_color = (80, 80, 255) if arousal_pct > 0.6 else (200, 200, 80)
    cv2.rectangle(img, (x_start, h - 38), (x_start + a_bar_w, h - 18), a_color, -1)
    cv2.putText(img, f"Arousal: {int(arousal_pct * 100)}%", (x_start + 2, h - 42),
                cv2.FONT_HERSHEY_SIMPLEX, 0.45, (200, 200, 220), 1)

    # Alert badge
    if fused.alert_level != PatientAlertLevel.NORMAL:
        alert_colors = {
            PatientAlertLevel.ATTENTION: (80, 255, 255),
            PatientAlertLevel.CONCERN: (80, 165, 255),
            PatientAlertLevel.URGENT: (80, 80, 255),
        }
        ac = alert_colors.get(fused.alert_level, (200, 200, 200))
        label = f"ALERT: {fused.alert_level.value.upper()}"
        cv2.putText(img, label, (w // 2 - 80, 68),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.65, ac, 2)

    # Face mesh landmarks (every 3rd for performance)
    if face_result.landmarks is not None:
        for i in range(0, len(face_result.landmarks), 3):
            pt = face_result.landmarks[i]
            cv2.circle(img, (int(pt[0]), int(pt[1])), 1, (255, 220, 100), -1)

    return img


# ─── Frame Processing Pipeline ───────────────────────────────

def process_frame(frame):
    """Process a single webcam frame through the full pipeline."""
    if frame is None:
        empty_html = (
            '<div style="font-family:system-ui;color:#64748b;padding:40px;text-align:center;">'
            'Waiting for webcam...</div>'
        )
        return None, "---", "---", "---", "---", "---", empty_html

    t0 = time.time()
    analyzer = get_face_analyzer()

    # Run analysis pipeline
    face_result = analyzer.analyze(frame, timestamp=t0)
    pain_result = pain_detector.assess(
        face_result.aus if face_result.face_detected else None, timestamp=t0
    )
    fused = fusion_engine.fuse(
        face_result=face_result,
        pain_assessment=pain_result,
        timestamp=t0,
    )
    pain_trend = pain_detector.get_trend()
    elapsed_ms = (time.time() - t0) * 1000.0

    # Draw overlay on video
    annotated = draw_overlay(frame.copy(), face_result, pain_result, fused)

    # Build quick-glance metrics
    comfort_text = f"{int(fused.comfort_level * 100)}%"
    pain_text = f"{pain_result.pspi_score:.1f} ({pain_result.pain_level.value})"
    arousal_text = f"{int(fused.arousal_level * 100)}%"
    engagement_text = f"{int(fused.engagement_level * 100)}%"
    alert_text = fused.alert_level.value.upper()

    # Build comprehensive HTML analysis
    analysis_html = build_analysis_html(face_result, pain_result, fused, pain_trend, elapsed_ms)

    return annotated, comfort_text, pain_text, arousal_text, engagement_text, alert_text, analysis_html


# ─── Text Analysis ───────────────────────────────────────────

def analyze_text(text):
    """Analyze caregiver notes for sentiment and pain/distress indicators."""
    if not text or not text.strip():
        return "", "", "", "", ""
    result = text_analyzer.analyze(text, time.time())
    valence = f"{int(result.valence * 100)}%"
    arousal = f"{int(result.arousal * 100)}%"
    confidence = f"{result.confidence:.0%}"
    flags = []
    if result.pain_mentioned:
        flags.append("Pain-related terms detected")
    if result.distress_mentioned:
        flags.append("Distress-related terms detected")
    flags_text = "\n".join(flags) if flags else "No pain/distress indicators"
    terms = ", ".join(result.key_terms) if result.key_terms else "None"
    return valence, arousal, confidence, flags_text, terms


# ─── Research Content (Markdown) ─────────────────────────────

RESEARCH_TAB1 = """
## Can Emotions Be Reliably Read From Faces?

### The Barrett Critique (2019) -- The Most Important Paper in This Field

> **Barrett, L.F., Adolphs, R., Marsella, S., Martinez, A.M., & Pollak, S.D.** (2019).
> Emotional Expressions Reconsidered: Challenges to Inferring Emotion From Human Facial Movements.
> *Psychological Science in the Public Interest*, 20(1), 1-68. **PMID: 31313636**

**Authors:** Lisa Feldman Barrett (Northeastern/MGH), Ralph Adolphs (Caltech), Stacy Marsella (Northeastern/Glasgow), Aleix M. Martinez (Ohio State), Seth D. Pollak (Wisconsin-Madison)

**What they found** (from verified abstract):

> *"People do sometimes smile when happy, frown when sad, scowl when angry...more than what would be expected by chance. **Yet how people communicate anger, disgust, fear, happiness, sadness, and surprise varies substantially across cultures, situations, and even across people within a single situation.** Furthermore, **similar configurations of facial movements variably express instances of more than one emotion category.**"*

**Key evidence:**
- People scowl during anger only **~30% of the time**
- The same facial configuration (wide eyes, open mouth) is labeled "fear" by Westerners but "threat/aggression" by Trobriand Islanders
- Forced-choice paradigms **inflated** apparent cross-cultural agreement in Ekman's original studies
- fMRI studies show **no consistent neural fingerprint** for any basic emotion category
- The face-to-emotion mapping is **many-to-many**, not one-to-one

**Bottom line:** The assumption underlying all commercial "emotion AI" -- that specific facial expressions reliably map to specific internal emotions -- is **not well-supported** by the totality of scientific evidence.

---

### Coles, Larsen & Lench (2019) -- Meta-Analysis of 138 Studies

> **Coles, N.A., Larsen, J.T., & Lench, H.C.** (2019). A meta-analysis of the facial feedback literature. *Psychological Bulletin*, 145(6), 610-651. **PMID: 30973236**

**Scale:** Meta-analysis of **286 effect sizes** from **138 studies**

- The overall effect of facial expressions on emotional experience was **statistically significant but small**
- Effects were **larger in the absence** of emotionally evocative stimuli
- Publication bias was detected

**Implication:** The face-to-emotion link exists but is **weak and context-dependent**.

---

### Ekman's Universal Emotions (1971) -- The Classical View

| Emotion | Key Facial Indicators |
|---|---|
| **Happiness** | Raised cheeks, crow's feet, lip corners up (Duchenne smile) |
| **Sadness** | Inner brow raised, lip corners down, chin raised |
| **Anger** | Brows lowered & together, eyes glaring, lips tightened |
| **Fear** | Brows raised & together, upper eyelids raised, mouth open |
| **Surprise** | Brows raised, eyes wide open, jaw dropped |
| **Disgust** | Nose wrinkled, upper lip raised, cheeks raised |

**Russell's Circumplex Model** (used in this system) maps emotions on two continuous dimensions: **Valence** (negative-positive) and **Arousal** (calm-excited). This is more scientifically defensible per Barrett's findings.
"""

RESEARCH_TAB2 = """
## Can We Actually Read Thoughts? The Science of Neural Decoding

> **There is a fundamental gap between emotion recognition (detecting affective states) and thought inference (determining cognitive content). Facial expressions may correlate with certain types of cognitive processing but cannot reveal specific thoughts.**

---

### Tang et al. (2023) -- Decoding Language from fMRI

> **Tang, J., LeBel, A., Jain, S., & Huth, A.G.** (2023). Semantic reconstruction of continuous language from non-invasive brain recordings. *Nature Neuroscience*, 26(5), 858-866. **PMID: 37127759**

- 3 participants, 16+ hours of fMRI per subject
- Decoder generates intelligible word sequences recovering **meaning** of perceived/imagined speech
- **Subject cooperation is REQUIRED** -- decoder fails without it
- Captures **semantic gist**, not verbatim thoughts

---

### Willett et al. (2023) -- Speech Neuroprosthesis

> **Willett, F.R., et al.** (2023). A high-performance speech neuroprosthesis. *Nature*, 620(7976), 1031-1036. **PMID: 37612500**

| Metric | Result |
|--------|--------|
| Word error rate (50-word vocab) | **9.1%** (2.7x fewer errors than previous SOTA) |
| Word error rate (125K-word vocab) | **23.8%** |
| Decoding speed | **62 words per minute** (3.4x previous record) |

**Requirement:** Brain surgery to implant intracortical microelectrode arrays.

---

### MindEye: Scotti et al. (2023)

> fMRI + CLIP + Diffusion models to reconstruct images a person is viewing. Requires 7T fMRI and 30-40 hours of per-person training data.
"""

RESEARCH_TAB3 = """
## Evidence-Based Verdict: What Is and Isn't Possible

### Scientifically Supported (Strong Evidence)

| Capability | Key Evidence | Real Accuracy |
|---|---|---|
| **Decoding viewed images** from fMRI | MindEye (NeurIPS 2023) | High semantic fidelity |
| **Decoding semantic gist** of thought | Tang et al. (*Nature Neuroscience*, 2023) | Paraphrase-level |
| **Decoding attempted speech** from implants | Willett et al. (*Nature*, 2023) | 9.1% WER, 62 wpm |
| **Distinguishing genuine vs. fake smiles** | FACS Duchenne vs. Pan-Am | Well-established |
| **Pain detection from faces** (non-verbal) | Prkachin & Solomon PSPI | Clinically validated |
| **Detecting attention direction** (gaze) | Eye tracking / face mesh | Strong evidence |
| **Detecting drowsiness/fatigue** | EAR (Eye Aspect Ratio) | Strong evidence |

### NOT Supported (No Scientific Basis)

| Claim | Status |
|---|---|
| **Reading specific thoughts from faces** | No scientific basis (Barrett et al.) |
| **Reliable deception detection from faces** | Debunked (~54% accuracy, barely above chance) |
| **Predicting criminality from faces** | Pseudoscience |
| **Covert mind reading** | Impossible with current tech |
| **Verbatim thought transcription** | Not achieved |

### Benchmark Accuracy

| Benchmark | SOTA Accuracy | Notes |
|---|---|---|
| RAF-DB | ~92.5% | 7-class expression + landmark |
| AffectNet-7 | ~67.5% | 7-class |
| FER2013 | ~76% | Human agreement only ~65% |
| CK+ | >99% | Saturated; not meaningful |
"""

RESEARCH_TAB4 = """
## Facial Action Coding System (FACS)

Developed by **Paul Ekman and Wallace Friesen (1978)**, FACS decomposes any facial expression into **Action Units (AUs)** -- individual muscle movements.

### Action Units Used in This System

| AU | Name | Muscle | Used For |
|----|------|--------|----------|
| AU1 | Inner Brow Raiser | Frontalis (medial) | Sadness, fear, surprise |
| AU2 | Outer Brow Raiser | Frontalis (lateral) | Surprise, fear |
| AU4 | Brow Lowerer | Corrugator supercilii | **Pain**, anger, concentration |
| AU6 | Cheek Raiser | Orbicularis oculi (orbital) | **Genuine smile**, **pain** |
| AU7 | Lid Tightener | Orbicularis oculi (palpebral) | **Pain**, squinting |
| AU9 | Nose Wrinkler | Levator labii superioris alaeque nasi | Disgust, **pain** |
| AU10 | Upper Lip Raiser | Levator labii superioris | Disgust, **pain** |
| AU12 | Lip Corner Puller | Zygomaticus major | **Smile** |
| AU15 | Lip Corner Depressor | Depressor anguli oris | Sadness |
| AU43 | Eyes Closed | Relaxation of levator palpebrae | **Pain**, sleep |

### Pain Detection: PSPI Scale (Used in This System)

**PSPI = AU4 + max(AU6, AU7) + max(AU9, AU10) + AU43**

| Score Range | Pain Level |
|-------------|------------|
| 0 - 1.5 | None |
| 1.5 - 4.0 | Mild |
| 4.0 - 8.0 | Moderate |
| 8.0 - 16.0 | Severe |

### Duchenne vs. Pan-Am Smile
- **Duchenne smile** (genuine): AU6 + AU12 -- includes crow's feet
- **Pan-Am smile** (fake): Only AU12 -- no crow's feet wrinkles
"""

RESEARCH_TAB5 = """
## Complete Verified Reference List

| # | Citation | Identifier |
|---|---------|------------|
| 1 | Barrett, L.F., et al. (2019). Emotional Expressions Reconsidered. *PSPI*, 20(1), 1-68. | **PMID: 31313636** |
| 2 | Tang, J., et al. (2023). Semantic reconstruction of continuous language from non-invasive brain recordings. *Nature Neuroscience*, 26(5), 858-866. | **PMID: 37127759** |
| 3 | Willett, F.R., et al. (2023). A high-performance speech neuroprosthesis. *Nature*, 620(7976), 1031-1036. | **PMID: 37612500** |
| 4 | Scotti, P.S., et al. (2023). MindEye: fMRI-to-Image with Contrastive Learning. *NeurIPS 2023*. | **arXiv: 2305.18274** |
| 5 | Coles, N.A., et al. (2019). Meta-analysis of facial feedback. *Psych Bulletin*, 145(6), 610-651. | **PMID: 30973236** |
| 6 | Ekman, P. & Friesen, W.V. (1978). *Facial Action Coding System*. | Book |
| 7 | Picard, R.W. (1997). *Affective Computing*. MIT Press. | Book |
| 8 | Prkachin, K.M. (1992). Facial expressions of pain. *Pain*, 51(3), 297-306. | Paper |
| 9 | Lucey, P., et al. (2011). Painful data: UNBC-McMaster pain archive. *IEEE FG*. | Paper |
| 10 | Poh, M.Z., et al. (2010). Non-contact cardiac pulse measurements. *Optics Express*, 18(10). | Paper |
| 11 | Poria, S., et al. (2017). Review of affective computing. *Information Fusion*, 37, 98-125. | Paper |
| 12 | Russell, J.A. (1980). Circumplex model of affect. *JPSP*, 39(6), 1161-1178. | Paper |
| 13 | Schuller, B., et al. (2018). Speech emotion recognition. *Communications of the ACM*. | Paper |

### Key Takeaway

> **Faces reveal emotional displays (not specific thoughts), and actual thought decoding requires
> brain imaging equipment, extensive per-person training, and active cooperation from the subject.
> No technology can read thoughts from facial expressions or covertly from a distance.**
"""

ABOUT_TEXT = """
## Multimodal Patient Care Monitoring System

A scientifically-grounded monitoring tool for caregivers combining multiple modalities.

| Module | Method | Scientific Basis |
|--------|--------|-----------------|
| **Face Analysis** | MediaPipe FaceLandmarker + AU estimation | FACS (Ekman & Friesen, 1978) |
| **Pain Detection** | PSPI scale from AUs | Prkachin & Solomon; Lucey et al. (2011) |
| **Voice Analysis** | Pitch, energy, spectral features | Schuller et al. (2018) |
| **Text Sentiment** | Domain-specific lexicon | Dimensional model (Russell, 1980) |
| **Fusion** | Confidence-weighted late fusion | Poria et al. (2017) |

### Design Principles

1. **No naive emotion labels** -- Per Barrett et al. (2019), facial configurations do NOT reliably map 1:1 to internal emotions. We report Action Units and dimensional states instead.
2. **Privacy-first** -- All processing is local. No video is stored.
3. **Transparent** -- Rule-based methods for explainability. Every threshold has a citation.
4. **Supplement, not replace** -- This system supports clinical judgment, it does not replace it.

### Disclaimer

This system detects facial Action Units and physiological indicators. Per Barrett et al. (2019, PMID: 31313636), facial configurations do NOT reliably map 1:1 to internal emotional states. All outputs should be interpreted as behavioral observations, not definitive diagnoses. Not FDA-approved for clinical use.
"""


# ─── Build Gradio UI ─────────────────────────────────────────

custom_css = """
.metric-box {
    background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
    border: 1px solid #334155;
    border-radius: 12px;
    padding: 16px;
    text-align: center;
}
.metric-box h3 { margin: 0; font-size: 0.85em; color: #94a3b8; }
.metric-box p { margin: 4px 0 0; font-size: 1.6em; font-weight: 700; color: #e2e8f0; }
.disclaimer {
    background: #1e293b;
    border-left: 4px solid #f59e0b;
    padding: 12px 16px;
    border-radius: 0 8px 8px 0;
    margin: 8px 0;
    font-size: 0.9em;
    color: #cbd5e1;
}
.analysis-panel {
    min-height: 200px;
}
"""

with gr.Blocks(
    title="Patient Care Monitor",
) as demo:

    gr.Markdown(
        "# Patient Care Monitor\n"
        "### Scientifically-grounded multimodal patient monitoring with comprehensive analysis output"
    )
    gr.HTML(
        '<div class="disclaimer">'
        '<strong>Scientific Disclaimer:</strong> This system detects facial Action Units and '
        'physiological indicators. Per Barrett et al. (2019, PMID: 31313636), facial configurations '
        'do NOT reliably map 1:1 to internal emotional states. All readings are behavioral '
        'observations, not diagnoses.'
        '</div>'
    )

    with gr.Tabs():
        # ── Tab 1: Live Monitor ──
        with gr.Tab("Live Monitor", id="monitor"):
            with gr.Row():
                with gr.Column(scale=3):
                    webcam_input = gr.Image(
                        sources=["webcam"],
                        streaming=True,
                        type="numpy",
                        label="Webcam Feed",
                    )
                with gr.Column(scale=3):
                    annotated_output = gr.Image(
                        label="Analysis Output (HUD Overlay)",
                        type="numpy",
                        interactive=False,
                    )

            # Quick-glance metrics row
            with gr.Row():
                comfort_out = gr.Textbox(label="Comfort", interactive=False, scale=1)
                pain_out = gr.Textbox(label="Pain (PSPI)", interactive=False, scale=1)
                arousal_out = gr.Textbox(label="Arousal", interactive=False, scale=1)
                engagement_out = gr.Textbox(label="Engagement", interactive=False, scale=1)
                alert_out = gr.Textbox(label="Alert Level", interactive=False, scale=1)

            # Comprehensive analysis panel
            gr.Markdown("### Comprehensive Analysis")
            analysis_panel = gr.HTML(
                value=(
                    '<div style="font-family:system-ui;color:#64748b;padding:40px;text-align:center;'
                    'background:#0f172a;border-radius:8px;">'
                    'Waiting for webcam stream... Enable your camera above to begin analysis.'
                    '</div>'
                ),
                elem_classes=["analysis-panel"],
            )

            webcam_input.stream(
                fn=process_frame,
                inputs=[webcam_input],
                outputs=[annotated_output, comfort_out, pain_out, arousal_out,
                         engagement_out, alert_out, analysis_panel],
            )

        # ── Tab 2: Text Analysis ──
        with gr.Tab("Text Analysis", id="text"):
            gr.Markdown("## Caregiver Notes - Text Analysis\nEnter caregiver notes or patient statements to analyze for pain/distress indicators and sentiment.")
            text_input = gr.Textbox(
                label="Enter text",
                placeholder="e.g., Patient complaining of sharp pain in lower back",
                lines=3,
            )
            analyze_btn = gr.Button("Analyze", variant="primary")

            with gr.Row():
                valence_out = gr.Textbox(label="Valence (Positivity)", interactive=False)
                text_arousal_out = gr.Textbox(label="Arousal", interactive=False)
                text_conf_out = gr.Textbox(label="Confidence", interactive=False)

            flags_out = gr.Textbox(label="Pain/Distress Flags", interactive=False, lines=2)
            terms_out = gr.Textbox(label="Key Terms Detected", interactive=False)

            analyze_btn.click(
                fn=analyze_text,
                inputs=[text_input],
                outputs=[valence_out, text_arousal_out, text_conf_out, flags_out, terms_out],
            )

        # ── Tab 3-7: Research ──
        with gr.Tab("Facial Emotion Science", id="r1"):
            gr.Markdown(RESEARCH_TAB1)

        with gr.Tab("Thought Decoding", id="r2"):
            gr.Markdown(RESEARCH_TAB2)

        with gr.Tab("What Works & What Doesn't", id="r3"):
            gr.Markdown(RESEARCH_TAB3)

        with gr.Tab("FACS & Action Units", id="r4"):
            gr.Markdown(RESEARCH_TAB4)

        with gr.Tab("References", id="r5"):
            gr.Markdown(RESEARCH_TAB5)

        with gr.Tab("About", id="about"):
            gr.Markdown(ABOUT_TEXT)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 7860))
    demo.launch(
        server_name="0.0.0.0",
        server_port=port,
        theme=gr.themes.Soft(
            primary_hue="blue",
            secondary_hue="slate",
            neutral_hue="slate",
            font=gr.themes.GoogleFont("Inter"),
        ),
        css=custom_css,
    )
