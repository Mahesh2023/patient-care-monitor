"""Privacy helpers.

Facial biometrics are "special category" data under GDPR Art. 9 and
HIPAA-relevant in a care context. The platform enforces:
  1. Explicit, per-session, time-limited consent stored as an auditable
     record (`monitoring_sessions.consent_*`), revocable at any time.
  2. Raw video/audio never leaves the browser: only numeric features are
     transmitted; only per-minute aggregates and alerts are persisted.
  3. Pseudonymised patients (display name only, no MRN / DOB fields).
  4. Client IPs are stored only as keyed HMAC digests.
  5. Automatic retention enforcement (see `app/services/maintenance.py`).
"""
from __future__ import annotations

import hashlib
import hmac

from .config import settings


def hash_ip(ip: str | None) -> str:
    key = settings.effective_jwt_secret.encode()
    return hmac.new(key, (ip or "unknown").encode(), hashlib.sha256).hexdigest()[:32]
