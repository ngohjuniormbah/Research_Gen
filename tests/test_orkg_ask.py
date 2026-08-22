"""Offline tests for NL -> ORKG retrieval (orkg.org egress is not required)."""
from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from httpx import AsyncClient

from app.schemas.orkg import SparqlResult
from app.services.llm.base import ChatMessage
from app.services.orkg.client import ORKGClient
from app.services.orkg.nl_query import ask_orkg, generate_sparql
from app.services.orkg.sparql import SparqlClient


class StubProvider:
    key = "stub"
    model = "stub-1"

    def __init__(self, out: str) -> None:
        self._out = out

    async def generate(self, messages: list[ChatMessage], **_: Any) -> str:
        return self._out

    async def stream(self, messages: list[ChatMessage], **_: Any) -> AsyncIterator[str]:
        yield self._out


class StubSparql(SparqlClient):
    def __init__(self, rows: list[dict[str, Any]], cols: list[str]) -> None:
        super().__init__("http://triplestore.invalid")
        self._rows, self._cols = rows, cols

    async def query(self, sparql: str, *, limit: int | None = None) -> SparqlResult:
        return SparqlResult(columns=self._cols, rows=self._rows, raw={})


class StubClient(ORKGClient):
    def __init__(self, items: list[dict[str, Any]]) -> None:
        super().__init__(oidc_url="http://o", client_id="c", api_url="http://a")
        self._items = items

    async def search(self, query: str, *, user_key: str | None = None, size: int = 20) -> dict:
        return {"content": self._items}


async def test_generate_sparql_strips_fences_and_none() -> None:
    p = StubProvider("```sparql\nSELECT ?x WHERE { ?x a ?y } LIMIT 5\n```")
    assert (await generate_sparql(p, "q")).startswith("SELECT ?x")
    assert await generate_sparql(StubProvider("NONE"), "q") == ""


async def test_ask_sparql_path_with_provenance() -> None:
    provider = StubProvider("SELECT ?paper WHERE { ?paper a <x> } LIMIT 5")
    sparql = StubSparql(rows=[{"paper": "https://orkg.org/resource/R123"}], cols=["paper"])
    out = await ask_orkg(
        request="ml for malaria", provider=provider, client=StubClient([]),
        sparql_client=sparql, size=5,
    )
    assert out.mode == "sparql"
    assert out.count == 1
    assert out.sparql and out.sparql.startswith("SELECT")
    src = out.records[0]["source"]
    assert src["type"] == "orkg-sparql" and src["resource_id"] == "R123"


async def test_ask_falls_back_to_search_when_sparql_rejected() -> None:
    # A non-SPARQL LLM answer is rejected by the real guard (no network hit), so we
    # fall back to ORKG search and still return grounded, provenance-tagged records.
    provider = StubProvider("Sure! Here is a literature review about malaria ...")
    real_guarded = SparqlClient("http://triplestore.invalid")  # guard runs before network
    out = await ask_orkg(
        request="malaria detection", provider=provider,
        client=StubClient([{"id": "R9", "title": "CNN for malaria", "year": 2021}]),
        sparql_client=real_guarded, size=10,
    )
    assert out.mode == "search"
    assert out.sparql_error and "rejected" in out.sparql_error.lower()
    assert out.count == 1
    src = out.records[0]["source"]
    assert src["type"] == "orkg" and src["resource_id"] == "R9"
    assert src["url"] == "https://orkg.org/resource/R9"


async def test_ask_endpoint(client: AsyncClient, auth_headers: dict, monkeypatch) -> None:
    async def fake_search(self, query, *, user_key=None, size=20):  # type: ignore[no-untyped-def]
        return {"content": [{"id": "R42", "title": "Deep learning for malaria", "year": 2022}]}

    monkeypatch.setattr(ORKGClient, "search", fake_search)
    resp = await client.post(
        "/api/v1/orkg/ask", headers=auth_headers, json={"query": "malaria detection"}
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["mode"] == "search"  # fake provider can't emit SPARQL -> guarded fallback
    assert body["count"] == 1
    assert body["records"][0]["source"]["type"] == "orkg"


async def test_ask_requires_auth(client: AsyncClient) -> None:
    assert (await client.post("/api/v1/orkg/ask", json={"query": "x"})).status_code == 401
