"""In-process OIDC token storage. Keyed by user id so each connected user keeps their
own ORKG session. (A durable store can replace this without touching callers.)"""

from __future__ import annotations

import time
from dataclasses import dataclass


@dataclass
class OidcToken:
    access_token: str
    refresh_token: str = ""
    expires_at: float = 0.0

    def is_expired(self, *, leeway: float = 30.0) -> bool:
        return time.time() >= (self.expires_at - leeway)


class TokenStore:
    def __init__(self) -> None:
        self._tokens: dict[str, OidcToken] = {}

    def get(self, key: str) -> OidcToken | None:
        return self._tokens.get(key)

    def set(self, key: str, token: OidcToken) -> None:
        self._tokens[key] = token

    def clear(self, key: str) -> None:
        self._tokens.pop(key, None)


_store = TokenStore()


def get_token_store() -> TokenStore:
    return _store
