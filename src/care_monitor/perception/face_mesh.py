"""MediaPipe FaceLandmarker wrapper: 478 landmarks + 52 ARKit blendshapes.

We use the Tasks API in VIDEO mode for temporal tracking consistency, and
force CPU delegate so the server runs on commodity cloud containers
(Render, Railway) without OpenGL dependencies.
"""
from __future__ import annotations
import os
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from ..config import settings
from ..logging_utils import get_logger

log = get_logger(__name__)

MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/face_landmarker/"
    "face_landmarker/float16/1/face_landmarker.task"
)
MODEL_PATH = settings.model_dir / "face_landmarker.task"

os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")


def ensure_model() -> Path:
    if MODEL_PATH.exists():
        return MODEL_PATH
    import urllib.request
    log.info("Downloading MediaPipe face_landmarker model ...")
    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    urllib.request.urlretrieve(MODEL_URL, MODEL_PATH)
    log.info(f"Saved to {MODEL_PATH}")
    return MODEL_PATH


class FacePerception:
    """Wraps MediaPipe FaceLandmarker in VIDEO running mode, CPU-only."""

    def __init__(self, num_faces: int = 1) -> None:
        import mediapipe as mp
        self._mp = mp
        ensure_model()
        BaseOptions = mp.tasks.BaseOptions
        Options = mp.tasks.vision.FaceLandmarkerOptions
        RunningMode = mp.tasks.vision.RunningMode

        base_opts = BaseOptions(
            model_asset_path=str(MODEL_PATH),
            delegate=BaseOptions.Delegate.CPU,
        )
        opts = Options(
            base_options=base_opts,
            running_mode=RunningMode.VIDEO,
            num_faces=num_faces,
            output_face_blendshapes=True,
            output_facial_transformation_matrixes=True,
            min_face_detection_confidence=0.5,
            min_face_presence_confidence=0.5,
            min_tracking_confidence=0.5,
        )
        try:
            self.landmarker = mp.tasks.vision.FaceLandmarker.create_from_options(opts)
            log.info("FacePerception ready (CPU delegate).")
        except Exception as e:
            log.warning(f"CPU delegate failed ({e}); falling back to auto delegate.")
            opts = Options(
                base_options=BaseOptions(model_asset_path=str(MODEL_PATH)),
                running_mode=RunningMode.VIDEO,
                num_faces=num_faces,
                output_face_blendshapes=True,
                output_facial_transformation_matrixes=True,
            )
            self.landmarker = mp.tasks.vision.FaceLandmarker.create_from_options(opts)

    def process(self, frame_bgr: np.ndarray, timestamp_ms: int) -> Any:
        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        mp_img = self._mp.Image(image_format=self._mp.ImageFormat.SRGB, data=rgb)
        return self.landmarker.detect_for_video(mp_img, timestamp_ms)

    def close(self) -> None:
        self.landmarker.close()
