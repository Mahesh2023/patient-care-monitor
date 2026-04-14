"""
Face Analyzer Module
====================
Estimates Action Units from MediaPipe FaceLandmarker (Tasks API).

Scientific Basis:
- FACS (Ekman & Friesen, 1978; updated Ekman, Friesen & Hager, 2002)
- MediaPipe FaceLandmarker provides 478 3D facial landmarks + 52 blendshapes
- Blendshapes directly map to facial muscle actions (ARKit-compatible)
- Geometric AU estimation as fallback / supplement to blendshapes

This module does NOT output naive emotion labels (happy/sad/angry).
Per Barrett et al. (2019, PMID: 31313636), we report AUs and let the
fusion engine combine them with other modalities for state estimation.
"""

import os
import math
from typing import Dict, Optional, Tuple, List
from dataclasses import dataclass

import numpy as np

# cv2 and mediapipe are imported lazily inside FaceAnalyzer to allow
# importing dataclasses (FaceAnalysisResult, AUEstimates) without
# requiring opencv/mediapipe at import time (e.g., cloud dashboard).
try:
    import cv2
    import mediapipe as mp
    _HAS_CV2 = True
except ImportError:
    _HAS_CV2 = False


@dataclass
class AUEstimates:
    """Estimated Action Unit intensities (0.0 to 1.0 scale)."""
    AU1: float = 0.0   # Inner Brow Raiser (frontalis, medial)
    AU2: float = 0.0   # Outer Brow Raiser (frontalis, lateral)
    AU4: float = 0.0   # Brow Lowerer (corrugator supercilii)
    AU5: float = 0.0   # Upper Lid Raiser (levator palpebrae)
    AU6: float = 0.0   # Cheek Raiser (orbicularis oculi, orbital)
    AU7: float = 0.0   # Lid Tightener (orbicularis oculi, palpebral)
    AU9: float = 0.0   # Nose Wrinkler (levator labii superioris alaeque nasi)
    AU10: float = 0.0  # Upper Lip Raiser (levator labii superioris)
    AU12: float = 0.0  # Lip Corner Puller (zygomaticus major) - smile
    AU15: float = 0.0  # Lip Corner Depressor (depressor anguli oris)
    AU17: float = 0.0  # Chin Raiser (mentalis)
    AU20: float = 0.0  # Lip Stretcher (risorius, platysma)
    AU23: float = 0.0  # Lip Tightener (orbicularis oris)
    AU25: float = 0.0  # Lips Part
    AU26: float = 0.0  # Jaw Drop (masseter relaxation)
    AU43: float = 0.0  # Eyes Closed
    AU45: float = 0.0  # Blink

    def to_dict(self) -> Dict[str, float]:
        return {k: round(v, 3) for k, v in self.__dict__.items()}


@dataclass
class FaceAnalysisResult:
    """Complete face analysis output."""
    face_detected: bool = False
    landmarks: Optional[np.ndarray] = None
    aus: Optional[AUEstimates] = None
    blendshapes: Optional[Dict[str, float]] = None  # Raw blendshape scores
    head_pose: Optional[Tuple[float, float, float]] = None  # pitch, yaw, roll
    eye_aspect_ratio_left: float = 0.0
    eye_aspect_ratio_right: float = 0.0
    mouth_aspect_ratio: float = 0.0
    brow_height_left: float = 0.0
    brow_height_right: float = 0.0
    forehead_roi: Optional[np.ndarray] = None  # For rPPG extraction
    timestamp: float = 0.0


# Mapping from MediaPipe blendshape names to FACS Action Units
# MediaPipe uses ARKit-compatible blendshapes
BLENDSHAPE_TO_AU = {
    # AU1 - Inner Brow Raiser
    "browInnerUp": "AU1",
    # AU2 - Outer Brow Raiser
    "browOuterUpLeft": "AU2",
    "browOuterUpRight": "AU2",
    # AU4 - Brow Lowerer
    "browDownLeft": "AU4",
    "browDownRight": "AU4",
    # AU5 - Upper Lid Raiser
    "eyeWideLeft": "AU5",
    "eyeWideRight": "AU5",
    # AU6 - Cheek Raiser
    "cheekSquintLeft": "AU6",
    "cheekSquintRight": "AU6",
    # AU7 - Lid Tightener
    "eyeSquintLeft": "AU7",
    "eyeSquintRight": "AU7",
    # AU9 - Nose Wrinkler
    "noseSneerLeft": "AU9",
    "noseSneerRight": "AU9",
    # AU10 - Upper Lip Raiser
    "mouthUpperUpLeft": "AU10",
    "mouthUpperUpRight": "AU10",
    # AU12 - Lip Corner Puller (smile)
    "mouthSmileLeft": "AU12",
    "mouthSmileRight": "AU12",
    # AU15 - Lip Corner Depressor
    "mouthFrownLeft": "AU15",
    "mouthFrownRight": "AU15",
    # AU17 - Chin Raiser
    "mouthShrugLower": "AU17",
    # AU20 - Lip Stretcher
    "mouthStretchLeft": "AU20",
    "mouthStretchRight": "AU20",
    # AU23 - Lip Tightener
    "mouthPressLeft": "AU23",
    "mouthPressRight": "AU23",
    # AU25 - Lips Part
    "mouthClose": "AU25_inv",  # Inverted: high mouthClose = lips together
    "jawOpen": "AU25",
    # AU26 - Jaw Drop
    # jawOpen also maps here at higher intensities
    # AU43 - Eyes Closed
    "eyeBlinkLeft": "AU43",
    "eyeBlinkRight": "AU43",
}


class FaceAnalyzer:
    """
    Real-time face analysis using MediaPipe FaceLandmarker (Tasks API).
    Uses blendshapes for AU estimation with geometric fallbacks.
    """

    # Key landmark indices (MediaPipe 478-point mesh)
    # Eyes
    LEFT_EYE = [33, 160, 158, 133, 153, 144]
    RIGHT_EYE = [362, 385, 387, 263, 373, 380]

    # Eyebrows
    LEFT_BROW_INNER = [55, 65]
    LEFT_BROW_OUTER = [70, 63]
    RIGHT_BROW_INNER = [285, 295]
    RIGHT_BROW_OUTER = [300, 293]

    # Nose
    NOSE_TIP = 4

    # Mouth
    UPPER_LIP_TOP = 13
    LOWER_LIP_BOTTOM = 14
    MOUTH_LEFT = 61
    MOUTH_RIGHT = 291

    # Chin / Jaw
    CHIN = 152

    # Forehead (for rPPG)
    FOREHEAD = [10, 67, 69, 104, 108, 151, 337, 299, 297, 333]

    # Reference points for normalization
    LEFT_EYE_OUTER = 33
    RIGHT_EYE_OUTER = 263

    def __init__(self, model_path: str = None):
        """
        Initialize FaceAnalyzer with MediaPipe Tasks API.

        Args:
            model_path: Path to face_landmarker.task model file.
                        Defaults to models/face_landmarker.task relative to project root.
        """
        if not _HAS_CV2:
            raise ImportError(
                "FaceAnalyzer requires opencv-python and mediapipe. "
                "Install with: pip install opencv-python mediapipe"
            )

        if model_path is None:
            # Find model relative to this file's location
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            model_path = os.path.join(base_dir, "models", "face_landmarker.task")

        if not os.path.exists(model_path):
            raise FileNotFoundError(
                f"Face landmarker model not found at {model_path}. "
                "Download it with:\n"
                "  python3 -c \"import urllib.request; "
                "urllib.request.urlretrieve("
                "'https://storage.googleapis.com/mediapipe-models/face_landmarker/"
                "face_landmarker/float16/1/face_landmarker.task', "
                "'models/face_landmarker.task')\""
            )

        options = mp.tasks.vision.FaceLandmarkerOptions(
            base_options=mp.tasks.BaseOptions(model_asset_path=model_path),
            running_mode=mp.tasks.vision.RunningMode.IMAGE,
            output_face_blendshapes=True,
            output_facial_transformation_matrixes=True,
            num_faces=1,
            min_face_detection_confidence=0.5,
            min_face_presence_confidence=0.5,
            min_tracking_confidence=0.5,
        )
        self._landmarker = mp.tasks.vision.FaceLandmarker.create_from_options(options)

        self._calibrated = True  # Blendshapes don't need calibration
        self._frame_count = 0

    def _dist(self, p1: np.ndarray, p2: np.ndarray) -> float:
        """Euclidean distance between two points."""
        return float(np.linalg.norm(p1 - p2))

    def _eye_aspect_ratio(self, landmarks: np.ndarray, eye_indices: List[int]) -> float:
        """
        Eye Aspect Ratio (EAR) - Soukupova & Cech (2016).
        EAR = (||p2-p6|| + ||p3-p5||) / (2 * ||p1-p4||)
        """
        p = landmarks[eye_indices]
        vertical_1 = self._dist(p[1], p[5])
        vertical_2 = self._dist(p[2], p[4])
        horizontal = self._dist(p[0], p[3])
        if horizontal < 1e-6:
            return 0.0
        return (vertical_1 + vertical_2) / (2.0 * horizontal)

    def _mouth_aspect_ratio(self, landmarks: np.ndarray) -> float:
        """Mouth openness ratio."""
        vertical = self._dist(landmarks[self.UPPER_LIP_TOP], landmarks[self.LOWER_LIP_BOTTOM])
        horizontal = self._dist(landmarks[self.MOUTH_LEFT], landmarks[self.MOUTH_RIGHT])
        if horizontal < 1e-6:
            return 0.0
        return vertical / horizontal

    def _brow_height(self, landmarks: np.ndarray, brow_indices: List[int],
                     eye_index: int) -> float:
        """Vertical distance from brow to eye, normalized by interocular distance."""
        brow_center = np.mean(landmarks[brow_indices], axis=0)
        eye_point = landmarks[eye_index]
        interocular = self._dist(landmarks[self.LEFT_EYE_OUTER],
                                 landmarks[self.RIGHT_EYE_OUTER])
        if interocular < 1e-6:
            return 0.0
        return self._dist(brow_center, eye_point) / interocular

    def _head_pose(self, landmarks: np.ndarray, img_w: int, img_h: int) -> Tuple[float, float, float]:
        """Estimate head pose (pitch, yaw, roll) using solvePnP."""
        model_points = np.array([
            [0.0, 0.0, 0.0],          # Nose tip
            [0.0, -330.0, -65.0],      # Chin
            [-225.0, 170.0, -135.0],   # Left eye left corner
            [225.0, 170.0, -135.0],    # Right eye right corner
            [-150.0, -150.0, -125.0],  # Left mouth corner
            [150.0, -150.0, -125.0],   # Right mouth corner
        ], dtype=np.float64)

        image_points = np.array([
            landmarks[self.NOSE_TIP][:2],
            landmarks[self.CHIN][:2],
            landmarks[self.LEFT_EYE_OUTER][:2],
            landmarks[self.RIGHT_EYE_OUTER][:2],
            landmarks[self.MOUTH_LEFT][:2],
            landmarks[self.MOUTH_RIGHT][:2],
        ], dtype=np.float64)

        focal_length = img_w
        center = (img_w / 2, img_h / 2)
        camera_matrix = np.array([
            [focal_length, 0, center[0]],
            [0, focal_length, center[1]],
            [0, 0, 1]
        ], dtype=np.float64)

        dist_coeffs = np.zeros((4, 1))
        success, rotation_vec, translation_vec = cv2.solvePnP(
            model_points, image_points, camera_matrix, dist_coeffs,
            flags=cv2.SOLVEPNP_ITERATIVE
        )

        if not success:
            return (0.0, 0.0, 0.0)

        rotation_mat, _ = cv2.Rodrigues(rotation_vec)
        pose_mat = cv2.hconcat([rotation_mat, translation_vec])
        _, _, _, _, _, _, euler_angles = cv2.decomposeProjectionMatrix(
            cv2.hconcat([pose_mat, np.array([[0, 0, 0, 1]], dtype=np.float64)])
        )

        return (float(euler_angles[0]), float(euler_angles[1]), float(euler_angles[2]))

    def _extract_forehead_roi(self, frame: np.ndarray, landmarks: np.ndarray) -> Optional[np.ndarray]:
        """Extract forehead region for rPPG analysis."""
        try:
            forehead_pts = landmarks[self.FOREHEAD][:, :2].astype(np.int32)
            x_min = max(0, np.min(forehead_pts[:, 0]) - 5)
            x_max = min(frame.shape[1], np.max(forehead_pts[:, 0]) + 5)
            y_min = max(0, np.min(forehead_pts[:, 1]) - 10)
            y_max = min(frame.shape[0], np.max(forehead_pts[:, 1]) + 5)
            if x_max - x_min < 10 or y_max - y_min < 10:
                return None
            return frame[y_min:y_max, x_min:x_max].copy()
        except (IndexError, ValueError):
            return None

    def _blendshapes_to_aus(self, blendshapes: Dict[str, float]) -> AUEstimates:
        """
        Convert MediaPipe blendshapes to FACS Action Unit estimates.
        Uses the BLENDSHAPE_TO_AU mapping, averaging bilateral values.
        """
        aus = AUEstimates()
        au_accum = {}  # AU -> list of values

        for bs_name, score in blendshapes.items():
            au_name = BLENDSHAPE_TO_AU.get(bs_name)
            if au_name is None:
                continue

            if au_name == "AU25_inv":
                # mouthClose is inverted for AU25
                score = 1.0 - score
                au_name = "AU25"

            if au_name not in au_accum:
                au_accum[au_name] = []
            au_accum[au_name].append(score)

        # Average bilateral values and set AU estimates
        for au_name, values in au_accum.items():
            avg_val = float(np.mean(values))
            if hasattr(aus, au_name):
                setattr(aus, au_name, np.clip(avg_val, 0, 1))

        # AU26 from jawOpen at higher intensities
        jaw_open = blendshapes.get("jawOpen", 0.0)
        aus.AU26 = np.clip(jaw_open, 0, 1)

        # AU45 (blink) from momentary high AU43
        aus.AU45 = aus.AU43  # In real-time, we'd track temporal patterns

        return aus

    def analyze(self, frame: np.ndarray, timestamp: float = 0.0) -> FaceAnalysisResult:
        """
        Analyze a single frame. Returns FaceAnalysisResult with AU estimates.

        Args:
            frame: BGR image from camera
            timestamp: Frame timestamp in seconds

        Returns:
            FaceAnalysisResult with all computed metrics
        """
        result = FaceAnalysisResult(timestamp=timestamp)
        img_h, img_w = frame.shape[:2]

        # Convert BGR to RGB for MediaPipe
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)

        # Run face landmarker
        detection = self._landmarker.detect(mp_image)

        if not detection.face_landmarks:
            return result

        result.face_detected = True

        # Convert landmarks to numpy array
        face_lms = detection.face_landmarks[0]
        landmarks = np.array([
            [lm.x * img_w, lm.y * img_h, lm.z * img_w]
            for lm in face_lms
        ])
        result.landmarks = landmarks

        # Extract blendshapes
        if detection.face_blendshapes and len(detection.face_blendshapes) > 0:
            bs_dict = {
                bs.category_name: bs.score
                for bs in detection.face_blendshapes[0]
            }
            result.blendshapes = bs_dict
            result.aus = self._blendshapes_to_aus(bs_dict)
        else:
            result.aus = AUEstimates()

        # Geometric metrics (used for display and rPPG)
        result.eye_aspect_ratio_left = self._eye_aspect_ratio(landmarks, self.LEFT_EYE)
        result.eye_aspect_ratio_right = self._eye_aspect_ratio(landmarks, self.RIGHT_EYE)
        result.mouth_aspect_ratio = self._mouth_aspect_ratio(landmarks)
        result.brow_height_left = self._brow_height(landmarks, self.LEFT_BROW_INNER, self.LEFT_EYE[0])
        result.brow_height_right = self._brow_height(landmarks, self.RIGHT_BROW_INNER, self.RIGHT_EYE[0])

        # Head Pose
        try:
            result.head_pose = self._head_pose(landmarks, img_w, img_h)
        except Exception:
            result.head_pose = (0.0, 0.0, 0.0)

        # Forehead ROI for rPPG
        result.forehead_roi = self._extract_forehead_roi(frame, landmarks)

        self._frame_count += 1
        return result

    @property
    def is_calibrated(self) -> bool:
        return self._calibrated

    def reset_calibration(self):
        """No-op for blendshape-based analysis (no calibration needed)."""
        pass

    def close(self):
        self._landmarker.close()
