"""Head pose (pitch/yaw/roll) from MediaPipe facial transformation matrix."""
from __future__ import annotations
import math
from typing import Dict

import numpy as np


def head_pose_from_matrix(mat4: np.ndarray) -> Dict[str, float]:
    """Decompose 4x4 facial transformation matrix into Euler angles (degrees).

    Returns a dict with pitch, yaw, roll. Convention: MediaPipe Tasks returns
    column-major 4x4 rigid transform. We follow the OpenCV-style ZYX Euler
    convention and return degrees for UI readability.
    """
    m = np.asarray(mat4, dtype=np.float64).reshape(4, 4)
    r = m[:3, :3]
    sy = math.sqrt(r[0, 0] ** 2 + r[1, 0] ** 2)
    singular = sy < 1e-6
    if not singular:
        pitch = math.degrees(math.atan2(r[2, 1], r[2, 2]))
        yaw = math.degrees(math.atan2(-r[2, 0], sy))
        roll = math.degrees(math.atan2(r[1, 0], r[0, 0]))
    else:
        pitch = math.degrees(math.atan2(-r[1, 2], r[1, 1]))
        yaw = math.degrees(math.atan2(-r[2, 0], sy))
        roll = 0.0
    return {"pitch": float(pitch), "yaw": float(yaw), "roll": float(roll)}


def head_stable(head_pose: Dict[str, float], yaw_thresh: float = 20.0,
                pitch_thresh: float = 15.0) -> bool:
    return (abs(head_pose.get("yaw", 0.0)) < yaw_thresh
            and abs(head_pose.get("pitch", 0.0)) < pitch_thresh)
