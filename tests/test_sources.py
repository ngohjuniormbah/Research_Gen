"""Offline tests for multi-source scholarly retrieval (no external egress — the fetch
helpers are monkeypatched)."""
from __future__ import annotations

from typing import Any

import pytest
from httpx import AsyncClient

from app.services.sources import aggregate, arxiv, crossref, openalex

_OPENALEX = {
    "results": [
        {
            "title": "Deep learning for malaria detection",
            "display_name": "Deep learning for malaria detection",
            "publication_year": 2021,
            "doi": "https://doi.org/10.1/shared",
            "abstract_inverted_index": {"A": [0], "malaria": [1], "study": [2]},
            "authorships": [{"author": {"display_name": "A. Author"}}],
            "primary_location": {"source": {"display_name": "Nature"}},
            "id": "https://openalex.org/W1",
        }
    ]
}
_CROSSREF = {
    "message": {
        "items": [
            {
                "title": ["A different malaria paper"],
                "DOI": "10.2/unique",
                "abstract": "<jats:p>Abstract text</jats:p>",
                "author": [{"given": "B.", "family": "Writer"}],
                "issued": {"date-parts": [[2020]]},
                "container-title": ["Journal of Tests"],
                "URL": "https://doi.org/10.2/unique",
            },
            {  # same DOI as the OpenAlex hit -> should be de-duplicated
                "title": ["Deep learning for malaria detection"],
                "DOI": "10.1/shared",
                "issued": {"date-parts": [[2021]]},
            },
        ]
    }
}
_ARXIV = """<?xml version='1.0'?>
<feed xmlns='http://www.w3.org/2005/Atom' xmlns:arxiv='http://arxiv.org/schemas/atom'>
  <entry>
    <title>Preprint on malaria nets</title>
    <summary>We study nets.</summary>
    <id>http://arxiv.org/abs/2101.00001</id>
    <published>2021-01-01T00:00:00Z</published>
    <author><name>C. Preprint</name></author>
  </entry>
</feed>"""


@pytest.fixture(autouse=True)
def _patch_fetch(monkeypatch):
    async def fake_json(url: str, params: dict[str, Any]):
        if "openalex" in url:
            return _OPENALEX
        if "crossref" in url:
            return _CROSSREF
        return {}

    async def fake_text(url: str, params: dict[str, Any]):
        return _ARXIV

    # Patch where each module looked the helper up (imported by name).
    monkeypatch.setattr(openalex, "fetch_json", fake_json)
    monkeypatch.setattr(crossref, "fetch_json", fake_json)
    monkeypatch.setattr(arxiv, "fetch_text", fake_text)


async def test_openalex_reconstructs_abstract() -> None:
    recs = await openalex.search("malaria", size=5)
    assert recs[0]["abstract"] == "A malaria study"
    assert recs[0]["doi"] == "10.1/shared"
    assert recs[0]["provider"] == "OpenAlex"


async def test_crossref_strips_html_abstract() -> None:
    recs = await crossref.search("malaria", size=5)
    assert recs[0]["abstract"] == "Abstract text"
    assert recs[0]["year"] == 2020
    assert recs[0]["provider"] == "Crossref"


async def test_arxiv_parses_atom() -> None:
    recs = await arxiv.search("malaria", size=5)
    assert recs[0]["title"] == "Preprint on malaria nets"
    assert recs[0]["year"] == 2021
    assert recs[0]["provider"] == "arXiv"


async def test_aggregate_merges_and_dedupes() -> None:
    records, used = await aggregate.search_sources("malaria", size=5)
    assert set(used) == {"openalex", "crossref", "arxiv"}
    dois = [r["doi"] for r in records if r["doi"]]
    assert dois.count("10.1/shared") == 1  # de-duplicated across OpenAlex + Crossref
    providers = {r["provider"] for r in records}
    assert providers == {"OpenAlex", "Crossref", "arXiv"}
    shared = next(r for r in records if r["doi"] == "10.1/shared")
    assert "Crossref" in shared.get("also_in", [])  # cross-source provenance recorded


async def test_one_provider_failing_does_not_sink_search(monkeypatch) -> None:
    async def boom(url: str, params: dict[str, Any]):
        raise RuntimeError("provider down")

    monkeypatch.setattr(crossref, "fetch_json", boom)
    records, used = await aggregate.search_sources("malaria", size=5)
    assert records  # still get OpenAlex + arXiv results


async def test_sources_endpoint(client: AsyncClient, auth_headers: dict) -> None:
    r = await client.get("/api/v1/sources/search?q=malaria&size=5", headers=auth_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["count"] >= 1
    assert set(body["providers"]) == {"openalex", "crossref", "arxiv"}


async def test_sources_requires_auth(client: AsyncClient) -> None:
    assert (await client.get("/api/v1/sources/search?q=x")).status_code == 401
