"""ORKG REST client with OIDC (Keycloak) token storage + refresh."""

from __future__ import annotations

import base64
import json
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


def _decode_jwt_payload(token: str) -> dict[str, Any]:
    """Decode JWT claims without external dependencies."""
    try:
        parts = token.split(".")
        if len(parts) >= 2:
            padding = "=" * (-len(parts[1]) % 4)
            return json.loads(base64.urlsafe_b64decode(parts[1] + padding))
    except Exception:
        pass
    return {}


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

    async def connect(self, user_key: str, username: str, password: str) -> tuple[OidcToken, dict[str, Any]]:
        """Exchange username/password for an OIDC token and decode claims."""
        payload = {
            "grant_type": "password",
            "client_id": self._client_id,
            "username": username,
            "password": password,
            "scope": "openid",
        }
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(self._token_endpoint, data=payload)
        if resp.status_code >= 400:
            raise ORKGAuthError(
                f"ORKG authentication failed ({resp.status_code}): {resp.text[:300]}"
            )

        token_data = resp.json()
        token = await self._store_token(user_key, token_data)
        claims = _decode_jwt_payload(token.access_token)
        return token, claims

    async def _refresh(self, user_key: str, token: OidcToken) -> OidcToken:
        if not token.refresh_token:
            raise ORKGAuthError(
                "Token expired and no refresh token available; please reconnect."
            )
        payload = {
            "grant_type": "refresh_token",
            "client_id": self._client_id,
            "refresh_token": token.refresh_token,
            "scope": "openid",
        }
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(self._token_endpoint, data=payload)
        if resp.status_code >= 400:
            await self._store.aclear(user_key)
            raise ORKGAuthError(
                "Token refresh failed; please reconnect your ORKG account."
            )
        return await self._store_token(user_key, resp.json())

    async def disconnect(self, user_key: str) -> None:
        """Revoke the stored ORKG session for this user."""
        await self._store.aclear(user_key)

    async def connection_info(self, user_key: str) -> dict[str, Any]:
        """Return full connection status and user identity."""
        token = await self._store.aget(user_key)
        if token is None or not token.access_token:
            return {"connected": False, "expires_in": 0, "username": None, "email": None}

        if token.is_expired():
            try:
                token = await self._refresh(user_key, token)
            except Exception:
                return {"connected": False, "expires_in": 0, "username": None, "email": None}

        claims = _decode_jwt_payload(token.access_token)
        username = claims.get("preferred_username") or claims.get("name")
        email = claims.get("email")

        return {
            "connected": True,
            "expires_in": max(0, int(token.expires_at - time.time())),
            "username": username,
            "email": email,
        }

    async def access_token(self, user_key: str) -> str | None:
        """Return a valid access token, refreshing if needed. None if not connected."""
        token = await self._store.aget(user_key)
        if token is None or not token.access_token:
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
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.get(
                f"{self._api_url}/resources/{resource_id}",
                headers=await self._headers(user_key),
            )
        resp.raise_for_status()
        return resp.json()

    async def get_comparison(
        self, comparison_id: str, *, user_key: str | None = None
    ) -> dict[str, Any]:
        """Fetch comparison resource from ORKG comparisons API if not found under resources."""
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.get(
                f"{self._api_url}/comparisons/{comparison_id}",
                headers=await self._headers(user_key),
            )
        resp.raise_for_status()
        return resp.json()

    async def get_statements(
        self, subject_id: str, *, user_key: str | None = None, size: int = 1000
    ) -> list[dict[str, Any]]:
        """Fetch statements for a subject. Default size increased to 1000 for large comparison tables."""
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.get(
                f"{self._api_url}/statements/subject/{subject_id}",
                params={"size": size},
                headers=await self._headers(user_key),
            )
        resp.raise_for_status()
        data = resp.json()
        items = data.get("content", data) if isinstance(data, dict) else data
        return items if isinstance(items, list) else []
