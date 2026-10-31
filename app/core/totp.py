"""TOTP (RFC 6238 / RFC 4226) + recovery codes + secret encryption at rest.

Implemented on the standard library (HMAC-SHA1, 30 s step, 6 digits) to
avoid an extra dependency; compatible with Google Authenticator, Authy,
1Password, Microsoft Authenticator, etc.

Replay protection: the last accepted time-step is stored per user and any
code for a step <= that value is rejected.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
import struct
import time
from urllib.parse import quote

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.hashes import SHA256
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from src.care_monitor.config import settings

STEP, DIGITS, ISSUER = 30, 6, "CARE-MM"


def generate_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def _code(secret_b32: str, step: int) -> str:
    key = base64.b32decode(secret_b32 + "=" * (-len(secret_b32) % 8), casefold=True)
    digest = hmac.new(key, struct.pack(">Q", step), hashlib.sha1).digest()
    off = digest[-1] & 0x0F
    val = struct.unpack(">I", digest[off:off + 4])[0] & 0x7FFFFFFF
    return str(val % 10 ** DIGITS).zfill(DIGITS)


def code_at(secret_b32: str, t: float | None = None) -> str:
    return _code(secret_b32, int((time.time() if t is None else t) // STEP))


def verify(secret_b32: str, code: str, last_step: int = 0, window: int = 1,
           t: float | None = None) -> int | None:
    """Return the matched time-step (to store as last_step) or None."""
    code = (code or "").strip().replace(" ", "")
    if not (code.isdigit() and len(code) == DIGITS):
        return None
    now = int((time.time() if t is None else t) // STEP)
    for step in range(now - window, now + window + 1):
        if step > last_step and hmac.compare_digest(_code(secret_b32, step), code):
            return step
    return None


def provisioning_uri(secret_b32: str, account: str) -> str:
    return (f"otpauth://totp/{quote(ISSUER)}:{quote(account)}?secret={secret_b32}"
            f"&issuer={quote(ISSUER)}&algorithm=SHA1&digits={DIGITS}&period={STEP}")


# ---- recovery codes -------------------------------------------------
def new_recovery_codes(n: int = 8) -> tuple[list[str], list[str]]:
    """(plaintext codes to show once, sha256 digests to store)."""
    codes = [f"{secrets.token_hex(4)}-{secrets.token_hex(4)}" for _ in range(n)]
    return codes, [hash_recovery(c) for c in codes]


def hash_recovery(code: str) -> str:
    return hashlib.sha256(code.strip().lower().encode()).hexdigest()


# ---- secret encryption at rest (AES-256-GCM, HKDF-derived key) -------
def _key() -> bytes:
    material = (settings.data_encryption_key or settings.effective_jwt_secret).encode()
    return HKDF(algorithm=SHA256(), length=32, salt=b"care-mm/v1", info=b"totp-secret").derive(material)


def encrypt(plaintext: str) -> str:
    nonce = os.urandom(12)
    return base64.urlsafe_b64encode(nonce + AESGCM(_key()).encrypt(nonce, plaintext.encode(), b"totp")).decode()


def decrypt(token: str) -> str:
    raw = base64.urlsafe_b64decode(token.encode())
    return AESGCM(_key()).decrypt(raw[:12], raw[12:], b"totp").decode()
