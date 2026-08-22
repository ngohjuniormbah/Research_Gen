"""Offline tests for ORKG reference resolution (no orkg.org egress needed)."""
from __future__ import annotations

from typing import Any

from httpx import AsyncClient

from app.services.orkg.client import ORKGClient
from app.services.orkg.resolve import classify_input, resolve_many, split_inputs


class StubClient(ORKGClient):
    def __init__(self, resources: dict[str, dict], search_hits: dict[str, dict]) -> None:
        super().__init__(oidc_url="http://o", client_id="c", api_url="http://a")
        self._resources = resources
        self._search_hits = search_hits

    async def get_resource(  # type: ignore[override]
        self, resource_id: str, *, user_key: str | None = None,
    ) -> dict[str, Any]:
        if resource_id in self._resources:
            return self._resources[resource_id]
        raise KeyError(resource_id)

    async def search(self, query: str, *, user_key: str | None = None, size: int = 20) -> dict:
        hit = self._search_hits.get(query)
        return {"content": [hit] if hit else []}


def test_classify_input() -> None:
    assert classify_input("https://orkg.org/paper/R1234") == ("orkg_id", "R1234")
    assert classify_input("R42") == ("orkg_id", "R42")
    assert classify_input("10.1109/ACCESS.2021.123456")[0] == "doi"
    assert classify_input("https://doi.org/10.1/abc")[0] == "doi"
    title = "Deep learning for malaria detection"
    assert classify_input(title) == ("title", title)


def test_split_inputs_preserves_titles_with_commas() -> None:
    text = "R1, R2, R3\nDeep learning, a survey of methods\nhttps://orkg.org/paper/R9"
    parts = split_inputs(text)
    assert "R1" in parts and "R2" in parts and "R3" in parts
    assert "Deep learning, a survey of methods" in parts  # not split (title)
    assert "https://orkg.org/paper/R9" in parts


async def test_resolve_many_mixed() -> None:
    client = StubClient(
        resources={"R100": {"id": "R100", "label": "CNN for malaria", "doi": "10.1/x"}},
        search_hits={
            "malaria detection deep learning": {"id": "R200", "title": "DL malaria", "year": 2022},
        },
    )
    records, unresolved = await resolve_many(
        "R100\nmalaria detection deep learning\nR999", client=client,
    )
    assert len(records) == 3
    by_input = {r["input"]: r for r in records}
    assert by_input["R100"]["resolved"] is True
    assert by_input["R100"]["source"]["url"] == "https://orkg.org/resource/R100"
    assert by_input["malaria detection deep learning"]["orkg_id"] == "R200"
    assert by_input["R999"]["resolved"] is False  # not found -> reported, not fabricated
    assert "R999" in unresolved


async def test_resolve_endpoint(client: AsyncClient, auth_headers: dict, monkeypatch) -> None:
    async def fake_get_resource(self, rid, *, user_key=None):  # type: ignore[no-untyped-def]
        return {"id": rid, "label": "Resolved paper", "doi": "10.9/z"}

    monkeypatch.setattr(ORKGClient, "get_resource", fake_get_resource)
    resp = await client.post(
        "/api/v1/orkg/resolve", headers=auth_headers, json={"inputs": "R55"}
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["count"] == 1 and body["resolved"] == 1
    assert body["records"][0]["source"]["resource_id"] == "R55"


async def test_resolve_requires_auth(client: AsyncClient) -> None:
    assert (await client.post("/api/v1/orkg/resolve", json={"inputs": "R1"})).status_code == 401
