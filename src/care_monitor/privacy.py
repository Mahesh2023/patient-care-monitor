"""Privacy gate: consent TTL + frame redaction.

Facial biometrics are "special category" data under GDPR Art. 9 and
HIPAA-covered when used in a care context. This module enforces:
  1. Explicit opt-in consent per session with a hard TTL.
  2. No raw-frame persistence by default (`store_raw_frames=False`).
  3. Optional frame redaction for any logged still images
     (Gaussian-blurred eye + mouth regions).
"""
from __future__ import annotations
import time
import uuid
from dataclasses import dataclass, field
from typing import Dict, Optional

import numpy as np

from .config import settings


@dataclass
class ConsentRecord:
    session_id: str
    granted_at: float
    ttl_seconds: int
    purpose: str = "clinical_monitoring"
    ip_hash: str = ""

    def valid(self, now: Optional[float] = None) -> bool:
        now = time.time() if now is None else now
        return (now - self.granted_at) < self.ttl_seconds


class ConsentStore:
    def __init__(self) -> None:
        self._records: Dict[str, ConsentRecord] = {}

    def grant(self, session_id: Optional[str] = None,
              purpose: str = "clinical_monitoring",
              ip_hash: str = "") -> ConsentRecord:
        sid = session_id or str(uuid.uuid4())
        rec = ConsentRecord(
            session_id=sid,
            granted_at=time.time(),
            ttl_seconds=settings.consent_ttl_hours * 3600,
            purpose=purpose,
            ip_hash=ip_hash,
        )
        self._records[sid] = rec
        return rec

    def is_valid(self, session_id: str) -> bool:
        rec = self._records.get(session_id)
        return bool(rec and rec.valid())

    def revoke(self, session_id: str) -> bool:
        return self._records.pop(session_id, None) is not None

    def prune_expired(self) -> int:
        now = time.time()
        expired = [sid for sid, r in self._records.items() if not r.valid(now)]
        for sid in expired:
            self._records.pop(sid, None)
        return len(expired)


CONSENT = ConsentStore()


def redact_frame_for_log(frame_bgr: np.ndarray,
                         eye_bbox: Optional[tuple] = None,
                         mouth_bbox: Optional[tuple] = None) -> np.ndarray:
    """Return a copy of frame with eye/mouth regions Gaussian-blurred.

    Used only when the caller *explicitly* decides to persist a still
    (e.g., for an audit snapshot). Default pipeline never logs raw frames.
    """
    import cv2
    out = frame_bgr.copy()
    for bbox in (eye_bbox, mouth_bbox):
        if bbox is None:
            continue
        x, y, w, h = bbox
        roi = out[y:y + h, x:x + w]
        if roi.size:
            out[y:y + h, x:x + w] = cv2.GaussianBlur(roi, (31, 31), 0)
    return out
