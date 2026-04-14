"""
Patient Care Monitor - Configuration
=====================================
Scientifically-grounded thresholds based on FACS research (Ekman & Friesen, 1978),
Prkachin & Solomon Pain Intensity scale, and Barrett et al. (2019) guidelines.

IMPORTANT: This system reports Action Units and physiological indicators,
NOT naive emotion labels. Per Barrett et al. (2019, PMID: 31313636),
facial configurations do NOT reliably map 1:1 to internal emotional states.
"""

import os
from dataclasses import dataclass, field
from typing import Dict, List

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
LOG_DIR = os.path.join(DATA_DIR, "session_logs")


@dataclass
class FaceConfig:
    """MediaPipe Face Mesh configuration."""
    max_num_faces: int = 1
    refine_landmarks: bool = True
    min_detection_confidence: float = 0.5
    min_tracking_confidence: float = 0.5
    # Landmarks for AU estimation (MediaPipe 468-point face mesh indices)
    # Reference: https://github.com/google/mediapipe/blob/master/mediapipe/modules/face_geometry/data/canonical_face_model_uv_visualization.png
    inner_brow_left: List[int] = field(default_factory=lambda: [55, 65, 52, 53])
    inner_brow_right: List[int] = field(default_factory=lambda: [285, 295, 282, 283])
    outer_brow_left: List[int] = field(default_factory=lambda: [70, 63, 105, 66])
    outer_brow_right: List[int] = field(default_factory=lambda: [300, 293, 334, 296])
    nose_tip: List[int] = field(default_factory=lambda: [1, 4, 5, 195])
    upper_lip: List[int] = field(default_factory=lambda: [13, 14, 312, 82])
    lower_lip: List[int] = field(default_factory=lambda: [14, 17, 87, 317])
    left_eye: List[int] = field(default_factory=lambda: [33, 160, 158, 133, 153, 144])
    right_eye: List[int] = field(default_factory=lambda: [362, 385, 387, 263, 373, 380])
    jaw: List[int] = field(default_factory=lambda: [152, 148, 176, 377, 400, 378])
    mouth_corners: List[int] = field(default_factory=lambda: [61, 291])


@dataclass
class PainConfig:
    """
    Pain detection thresholds based on Prkachin & Solomon Pain Intensity (PSPI) scale.
    PSPI = AU4 + max(AU6, AU7) + max(AU9, AU10) + AU43
    Score range: 0-16. Clinical pain threshold typically >= 2.
    References:
        - Prkachin (1992). The consistency of facial expressions of pain.
        - Lucey et al. (2011). Painful data: The UNBC-McMaster shoulder pain expression archive.
    """
    pspi_mild_threshold: float = 1.5
    pspi_moderate_threshold: float = 4.0
    pspi_severe_threshold: float = 8.0
    alert_threshold: float = 3.0  # Trigger caregiver alert above this


@dataclass
class VoiceConfig:
    """Voice analysis configuration."""
    sample_rate: int = 16000
    frame_duration_ms: int = 30
    # Pitch thresholds (Hz) - based on speech prosody research
    distress_pitch_threshold: float = 300.0  # High pitch may indicate distress
    low_energy_threshold: float = 0.01  # Very low energy may indicate withdrawal
    analysis_window_sec: float = 3.0


@dataclass
class RPPGConfig:
    """
    Remote Photoplethysmography configuration.
    Based on: Poh et al. (2010). Non-contact, automated cardiac pulse measurements
    using video imaging and blind source separation. Optics Express.
    """
    buffer_size: int = 300  # frames (~10s at 30fps)
    fps: float = 30.0
    bandpass_low: float = 0.7  # Hz (~42 bpm)
    bandpass_high: float = 4.0  # Hz (~240 bpm)
    # Forehead ROI for color signal extraction
    forehead_landmarks: List[int] = field(default_factory=lambda: [10, 67, 69, 104, 108, 151, 337, 299, 297, 333])
    # Normal resting heart rate range
    normal_hr_low: float = 60.0
    normal_hr_high: float = 100.0
    stress_hr_threshold: float = 100.0


@dataclass
class AlertConfig:
    """Alert system configuration."""
    pain_alert_enabled: bool = True
    distress_alert_enabled: bool = True
    hr_alert_enabled: bool = True
    # Cooldown period between alerts (seconds) to avoid alert fatigue
    alert_cooldown_sec: float = 30.0
    # How many consecutive frames must trigger before alerting
    consecutive_frames_threshold: int = 5
    # Log retention (days)
    log_retention_days: int = 30


@dataclass
class SystemConfig:
    """Top-level system configuration."""
    face: FaceConfig = field(default_factory=FaceConfig)
    pain: PainConfig = field(default_factory=PainConfig)
    voice: VoiceConfig = field(default_factory=VoiceConfig)
    rppg: RPPGConfig = field(default_factory=RPPGConfig)
    alerts: AlertConfig = field(default_factory=AlertConfig)
    # Processing
    process_every_n_frames: int = 2  # Skip frames for performance
    dashboard_port: int = 8501
    # Privacy: all processing is local, no data leaves the machine
    privacy_mode: bool = True
    save_video: bool = False  # Never save raw video by default
    save_frames: bool = False


# Scientific disclaimers shown in the UI
DISCLAIMERS = {
    "general": (
        "SCIENTIFIC DISCLAIMER: This system detects facial Action Units and "
        "physiological indicators. Per Barrett et al. (2019, Psychological Science "
        "in the Public Interest, PMID: 31313636), facial configurations do NOT "
        "reliably map 1:1 to internal emotional states. All outputs should be "
        "interpreted as behavioral observations, not definitive diagnoses."
    ),
    "pain": (
        "Pain estimates use the PSPI scale (Prkachin & Solomon), which is clinically "
        "validated for non-verbal patients but should supplement, not replace, "
        "professional clinical assessment."
    ),
    "heart_rate": (
        "Heart rate is estimated via remote photoplethysmography (rPPG) from facial "
        "skin color changes. This is an approximation and should not be used for "
        "medical diagnosis. Accuracy is affected by lighting, movement, and skin tone."
    ),
}
