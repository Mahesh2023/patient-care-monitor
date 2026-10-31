"""Password policy (OWASP ASVS 5.0 V6.2 / NIST SP 800-63B).

* length 10-128, any characters, no composition rules (ASVS 6.2.5);
* rejected if in the top common-password list (ASVS 6.2.4; NCSC 100k list
  filtered to policy length) or built from context-specific words / the
  user's own email (ASVS 6.1.2);
* optionally rejected if present in known breaches via the Pwned Passwords
  k-anonymity range API — only the first 5 hex chars of the SHA-1 leave the
  server, with response padding enabled. Fail-open on network errors so an
  outage of the third party never blocks sign-up.
"""
from __future__ import annotations

import hashlib
import re
from functools import lru_cache
from pathlib import Path

import httpx

from src.care_monitor.config import settings
from src.care_monitor.logging_utils import get_logger

log = get_logger(__name__)
_DATA = Path(__file__).parent / "data" / "common_passwords.txt"
CONTEXT_WORDS = ("caremm", "care-mm", "patient", "password", "monitor", "caregiver", "qwerty")


class WeakPassword(ValueError):
    pass


@lru_cache(maxsize=1)
def _common() -> frozenset[str]:
    return frozenset(line.strip() for line in _DATA.read_text(encoding="utf-8").splitlines()
                     if line and not line.startswith("#"))


def check_local(password: str, email: str = "") -> None:
    low = password.lower()
    if low in _common():
        raise WeakPassword("This password is too common. Choose a longer, unique passphrase.")
    core = re.sub(r"[^a-z]", "", low)
    local = email.split("@")[0].lower()
    if core and (core in CONTEXT_WORDS or (len(local) >= 4 and (local in low))):
        raise WeakPassword("Password must not be based on your email address or the service name.")
    if len(set(password)) < 4:
        raise WeakPassword("Password has too few distinct characters.")


async def breached_count(password: str) -> int:
    """Times the password appears in known breaches (0 if unknown / on error)."""
    if not settings.hibp_enabled:
        return 0
    sha = hashlib.sha1(password.encode(), usedforsecurity=False).hexdigest().upper()
    prefix, suffix = sha[:5], sha[5:]
    try:
        async with httpx.AsyncClient(timeout=2.5) as c:
            r = await c.get(f"https://api.pwnedpasswords.com/range/{prefix}",
                            headers={"Add-Padding": "true", "User-Agent": "care-mm-password-check"})
            r.raise_for_status()
    except Exception as e:
        log.warning("pwned-passwords check skipped: %s", type(e).__name__)
        return 0
    for line in r.text.splitlines():
        h, _, n = line.partition(":")
        if h.strip() == suffix:
            return int(n.strip() or 0)
    return 0


async def validate_password(password: str, email: str = "") -> None:
    check_local(password, email)
    if await breached_count(password) > 0:
        raise WeakPassword("This password has appeared in a data breach. Please choose a different one.")
