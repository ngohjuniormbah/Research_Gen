"""ORKG REST client with OIDC (Keycloak) token storage + refresh.

Auth uses the OpenID Connect token endpoint at
``{oidc_url}/protocol/openid-connect/token``. Tokens are cached per user and refreshed
transparently when expired."""

from __future__ import annotations

import time
from typing import Any

import httpx

from .tokens import OidcToken, TokenStore, get_token_store


class ORKGAuthError(Exception):
    pass


class ORKGClient:
    def __init__(
        self,
        *,
        oidc_url: str,
        client_id: str,
        api_url: str,
        token_store: TokenStore | None = None,
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

    def _store_token(self, user_key: str, data: dict[str, Any]) -> OidcToken:
        token = OidcToken(
            access_token=str(data["access_token"]),
            refresh_token=str(data.get("refresh_token", "")),
            expires_at=time.time() + float(data.get("expires_in", 0)),
        )
        self._store.set(user_key, token)
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
        return self._store_token(user_key, resp.json())

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
            self._store.clear(user_key)
            raise ORKGAuthError("token refresh failed; reconnect")
        return self._store_token(user_key, resp.json())

    async def access_token(self, user_key: str) -> str | None:
        """Return a valid access token, refreshing if needed. None if not connected."""
        token = self._store.get(user_key)
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
