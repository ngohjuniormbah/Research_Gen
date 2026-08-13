"""Symmetric encryption for secrets at rest (ORKG OIDC tokens).

Uses Fernet (AES-128-CBC + HMAC) when FERNET_KEY is set. With no key configured — dev
only — it falls back to a clearly-marked passthrough so the app still runs."""

from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken

_PLAINTEXT_PREFIX = "plain:"


class TokenCipher:
    def __init__(self, key: str) -> None:
        self._fernet: Fernet | None = Fernet(key.encode("utf-8")) if key else None

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
