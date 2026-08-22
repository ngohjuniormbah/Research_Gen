"""ORKG connection lifecycle (mocked OIDC) and the ORKG draft/export workflow."""
from __future__ import annotations

import time

from httpx import AsyncClient

from app.services.orkg.client import ORKGClient
from app.services.orkg.tokens import OidcToken


async def test_connection_status_and_disconnect(
    client: AsyncClient, auth_headers: dict, monkeypatch
) -> None:
    async def fake_connect(self, user_key, username, password):  # type: ignore[no-untyped-def]
        await self._store.aset(
            user_key,
            OidcToken(access_token="AT", refresh_token="RT", expires_at=time.time() + 3600),
        )
        return await self._store.aget(user_key)

    monkeypatch.setattr(ORKGClient, "connect", fake_connect)

    # initially not connected
    st = await client.get("/api/v1/orkg/connection", headers=auth_headers)
    assert st.status_code == 200 and st.json()["connected"] is False

    # connect (credentials go to the backend only)
    c = await client.post(
        "/api/v1/orkg/connect", headers=auth_headers,
        json={"username": "u", "password": "p"},
    )
    assert c.status_code == 200 and c.json()["connected"] is True

    st2 = await client.get("/api/v1/orkg/connection", headers=auth_headers)
    assert st2.json()["connected"] is True and st2.json()["expires_in"] > 0

    d = await client.post("/api/v1/orkg/disconnect", headers=auth_headers)
    assert d.status_code == 200 and d.json()["connected"] is False
    st3 = await client.get("/api/v1/orkg/connection", headers=auth_headers)
    assert st3.json()["connected"] is False


async def test_connection_requires_auth(client: AsyncClient) -> None:
    assert (await client.get("/api/v1/orkg/connection")).status_code == 401


async def test_orkg_draft_export(client: AsyncClient, auth_headers: dict) -> None:
    r = await client.post(
        "/api/v1/reviews", headers=auth_headers,
        json={"topic": "attention", "records": [{"title": "T", "abstract": "a", "year": 2020}]},
    )
    review_id = r.json()["result"]["review_id"]

    d = await client.get(f"/api/v1/reviews/{review_id}/orkg-draft", headers=auth_headers)
    assert d.status_code == 200
    assert "attachment" in d.headers.get("content-disposition", "")
    body = d.json()
    assert body["kind"] == "orkg_contribution_draft"
    assert body["status"] == "draft"
    assert "never auto-publishes" in body["note"].lower()
    assert body["content_markdown"]
    assert isinstance(body["sources"], list)
    assert body["provenance"]["review_id"] == review_id
