"""OIDC token storage with encryption at rest, keyed by user id so each connected user
keeps their own ORKG session.

Two backends implement the same async interface (``aget``/``aset``/``aclear``):

* :class:`TokenStore` — in-process, used in unit tests and as a fallback.
* :class:`DbTokenStore` — durable, backed by the ``orkg_tokens`` table, so a connection
  survives page refreshes, new browser sessions, and backend redeploys/instance recycles.

Access/refresh tokens are always encrypted via the configured cipher before storage."""

from __future__ import annotations

import time
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from ...config import get_settings
from ...core.crypto import TokenCipher
from ...models.orkg_token import OrkgToken


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
    """In-process token store. Kept for tests and as a non-durable fallback."""

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

    # Async interface used by ORKGClient (uniform across backends).
    async def aget(self, key: str) -> OidcToken | None:
        return self.get(key)

    async def aset(self, key: str, token: OidcToken) -> None:
        self.set(key, token)

    async def aclear(self, key: str) -> None:
        self.clear(key)


class DbTokenStore:
    """Durable token store backed by the ``orkg_tokens`` table.

    Bound to a request-scoped :class:`AsyncSession`; each call reads/writes a single row
    keyed by the caller's user id, encrypting/decrypting via the configured cipher."""

    def __init__(self, session: AsyncSession, cipher: TokenCipher) -> None:
        self._session = session
        self._cipher = cipher

    async def aget(self, key: str) -> OidcToken | None:
        row = await self._session.get(OrkgToken, key)
        if row is None:
            return None
        return OidcToken(
            access_token=self._cipher.decrypt(row.access_token_enc),
            refresh_token=self._cipher.decrypt(row.refresh_token_enc),
            expires_at=row.expires_at,
        )

    async def aset(self, key: str, token: OidcToken) -> None:
        access_enc = self._cipher.encrypt(token.access_token)
        refresh_enc = self._cipher.encrypt(token.refresh_token)
        row = await self._session.get(OrkgToken, key)
        if row is None:
            row = OrkgToken(user_key=key)
            self._session.add(row)
        row.access_token_enc = access_enc
        row.refresh_token_enc = refresh_enc
        row.expires_at = token.expires_at
        await self._session.commit()

    async def aclear(self, key: str) -> None:
        row = await self._session.get(OrkgToken, key)
        if row is not None:
            await self._session.delete(row)
            await self._session.commit()


_store: TokenStore | None = None


def get_token_store() -> TokenStore:
    """In-process fallback store (used when no DB session is available)."""
    global _store
    if _store is None:
        _store = TokenStore(TokenCipher(get_settings().fernet_key))
    return _store
