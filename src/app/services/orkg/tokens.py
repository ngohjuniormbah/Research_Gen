"""In-process OIDC token storage with encryption at rest. Keyed by user id so each
connected user keeps their own ORKG session. Access/refresh tokens are encrypted via the
configured cipher before they are held in memory. (A durable store can replace this
without touching callers.)"""

from __future__ import annotations

import time
from dataclasses import dataclass

from ...config import get_settings
from ...core.crypto import TokenCipher


@dataclass
class OidcToken:
    access_token: str
    refresh_token: str = ""
    expires_at: float = 0.0

    def is_expired(self, *, leeway: float = 30.0) -> bool:
        return time.time() >= (self.expires_at - leeway)


@dataclass
class _StoredToken:
    access_token_enc: str
    refresh_token_enc: str
    expires_at: float


class TokenStore:
    def __init__(self, cipher: TokenCipher) -> None:
        self._cipher = cipher
        self._tokens: dict[str, _StoredToken] = {}

    def get(self, key: str) -> OidcToken | None:
        stored = self._tokens.get(key)
        if stored is None:
            return None
        return OidcToken(
            access_token=self._cipher.decrypt(stored.access_token_enc),
            refresh_token=self._cipher.decrypt(stored.refresh_token_enc),
            expires_at=stored.expires_at,
        )

    def set(self, key: str, token: OidcToken) -> None:
        self._tokens[key] = _StoredToken(
            access_token_enc=self._cipher.encrypt(token.access_token),
            refresh_token_enc=self._cipher.encrypt(token.refresh_token),
            expires_at=token.expires_at,
        )

    def clear(self, key: str) -> None:
        self._tokens.pop(key, None)


_store: TokenStore | None = None


def get_token_store() -> TokenStore:
    global _store
    if _store is None:
        _store = TokenStore(TokenCipher(get_settings().fernet_key))
    return _store
