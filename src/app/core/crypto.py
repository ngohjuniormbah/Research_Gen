"""Symmetric encryption for secrets at rest (ORKG OIDC tokens).

Uses Fernet (AES-128-CBC + HMAC) when FERNET_KEY is set. With no key configured — dev
only — it falls back to a clearly-marked passthrough so the app still runs."""

from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

_PLAINTEXT_PREFIX = "plain:"


def _coerce_fernet_key(key: str) -> bytes:
    """Accept either a real Fernet key or ANY secret string. A non-Fernet secret is
    stretched into a valid 32-byte urlsafe key, so platform-generated secrets work."""
    raw = key.encode("utf-8")
    try:
        Fernet(raw)  # already a valid Fernet key
        return raw
    except (ValueError, TypeError):
        return base64.urlsafe_b64encode(hashlib.sha256(raw).digest())


class TokenCipher:
    def __init__(self, key: str) -> None:
        self._fernet: Fernet | None = Fernet(_coerce_fernet_key(key)) if key else None

    @property
    def active(self) -> bool:
        return self._fernet is not None

    def encrypt(self, value: str) -> str:
        if not value:
            return value
        if self._fernet is None:
            return _PLAINTEXT_PREFIX + value
        return self._fernet.encrypt(value.encode("utf-8")).decode("ascii")

    def decrypt(self, value: str) -> str:
        if not value:
            return value
        if value.startswith(_PLAINTEXT_PREFIX):
            return value[len(_PLAINTEXT_PREFIX) :]
        if self._fernet is None:
            return value
        try:
            return self._fernet.decrypt(value.encode("ascii")).decode("utf-8")
        except InvalidToken:
            return ""
