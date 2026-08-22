"""ORKG REST client with OIDC (Keycloak) token storage + refresh.

Auth uses the OpenID Connect token endpoint at
``{oidc_url}/protocol/openid-connect/token``. Tokens are cached per user and refreshed
transparently when expired."""

from __future__ import annotations

import time
from typing import Any, Protocol

import httpx

from .tokens import OidcToken, get_token_store


class _AsyncTokenStore(Protocol):
    async def aget(self, key: str) -> OidcToken | None: ...
    async def aset(self, key: str, token: OidcToken) -> None: ...
    async def aclear(self, key: str) -> None: ...


class ORKGAuthError(Exception):
    pass


class ORKGClient:
    def __init__(
        self,
        *,
        oidc_url: str,
        client_id: str,
        api_url: str,
        token_store: _AsyncTokenStore | None = None,
        timeout_s: float = 30.0,
    ) -> None:
        self._oidc_url = oidc_url.rstrip("/")
        self._client_id = client_id
        self._api_url = api_url.rstrip("/")
        self._store = token_store or get_token_store()
        self._timeout = timeout_s

    @property
    def _token_endpoint(self) -> str:
        return f"{self._oidc_url}/protocol/openid-connect/token"

    async def _store_token(self, user_key: str, data: dict[str, Any]) -> OidcToken:
        token = OidcToken(
            access_token=str(data["access_token"]),
            refresh_token=str(data.get("refresh_token", "")),
            expires_at=time.time() + float(data.get("expires_in", 0)),
        )
        await self._store.aset(user_key, token)
        return token

    async def connect(self, user_key: str, username: str, password: str) -> OidcToken:
        """Exchange username/password for an OIDC token (password grant) and store it."""
        payload = {
            "grant_type": "password",
            "client_id": self._client_id,
            "username": username,
            "password": password,
        }
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(self._token_endpoint, data=payload)
        if resp.status_code >= 400:
            raise ORKGAuthError(f"ORKG auth failed ({resp.status_code}): {resp.text[:300]}")
        return await self._store_token(user_key, resp.json())

    async def _refresh(self, user_key: str, token: OidcToken) -> OidcToken:
        if not token.refresh_token:
            raise ORKGAuthError("token expired and no refresh token available; reconnect")
        payload = {
            "grant_type": "refresh_token",
            "client_id": self._client_id,
            "refresh_token": token.refresh_token,
        }
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(self._token_endpoint, data=payload)
        if resp.status_code >= 400:
            await self._store.aclear(user_key)
            raise ORKGAuthError("token refresh failed; reconnect")
        return await self._store_token(user_key, resp.json())

    async def disconnect(self, user_key: str) -> None:
        """Revoke the stored ORKG session for this user (logout)."""
        await self._store.aclear(user_key)

    async def connection(self, user_key: str) -> tuple[bool, int]:
        """(connected, seconds_until_expiry) for this user's ORKG session."""
        token = await self._store.aget(user_key)
        if token is None:
            return False, 0
        return True, max(0, int(token.expires_at - time.time()))

    async def access_token(self, user_key: str) -> str | None:
        """Return a valid access token, refreshing if needed. None if not connected."""
        token = await self._store.aget(user_key)
        if token is None:
            return None
        if token.is_expired():
            token = await self._refresh(user_key, token)
        return token.access_token

    async def _headers(self, user_key: str | None) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        if user_key:
            token = await self.access_token(user_key)
            if token:
                headers["Authorization"] = f"Bearer {token}"
        return headers

    async def search(
        self, query: str, *, user_key: str | None = None, size: int = 20
    ) -> dict[str, Any]:
        """Full-text search over ORKG resources. Auth is optional (public read)."""
        params: dict[str, str | int] = {"q": query, "size": size}
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.get(
                f"{self._api_url}/resources",
                params=params,
                headers=await self._headers(user_key),
            )
        resp.raise_for_status()
        return resp.json()

    async def get_resource(
        self, resource_id: str, *, user_key: str | None = None
    ) -> dict[str, Any]:
        """Fetch a single ORKG resource by id (papers, comparisons, contributions and
        other resources are all addressable here). Public read; auth optional."""
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.get(
                f"{self._api_url}/resources/{resource_id}",
                headers=await self._headers(user_key),
            )
        resp.raise_for_status()
        return resp.json()
