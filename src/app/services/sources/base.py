"""Shared plumbing for real scholarly-source connectors (OpenAlex, Crossref, arXiv, …).

Each connector fetches from a real public API and normalizes to a common record shape so
the workspace can present results from many sources at once — each tagged with its
provider and a link back to the origin (provenance), never fabricated.

HTTP goes through the module-level ``fetch_json``/``fetch_text`` helpers so tests can
monkeypatch them without any network egress."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx

# A short, polite User-Agent — several scholarly APIs ask for one and rate-limit anonymous
# clients harder. A contact mailbox is the OpenAlex/Crossref "polite pool" convention.
USER_AGENT = "WorldModelOfScience/1.0 (mailto:research@worldmodelofscience.app)"
_TIMEOUT = 20.0


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


async def fetch_json(url: str, params: dict[str, Any]) -> Any:
    async with httpx.AsyncClient(timeout=_TIMEOUT, headers={"User-Agent": USER_AGENT}) as c:
        resp = await c.get(url, params=params)
    resp.raise_for_status()
    return resp.json()


async def fetch_text(url: str, params: dict[str, Any]) -> str:
    async with httpx.AsyncClient(timeout=_TIMEOUT, headers={"User-Agent": USER_AGENT}) as c:
        resp = await c.get(url, params=params)
    resp.raise_for_status()
    return resp.text


def clean_doi(value: str | None) -> str:
    if not value:
        return ""
    v = value.strip()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
        if v.lower().startswith(prefix):
            v = v[len(prefix):]
    return v.strip()


def record(
    *,
    title: str,
    provider: str,
    provider_key: str,
    url: str | None = None,
    abstract: str = "",
    authors: list[str] | None = None,
    year: int | None = None,
    venue: str = "",
    doi: str = "",
) -> dict[str, Any]:
    """Normalize one result into the shared record shape the workspace consumes."""
    return {
        "title": (title or "").strip(),
        "abstract": (abstract or "").strip(),
        "authors": authors or [],
        "year": year,
        "venue": (venue or "").strip(),
        "doi": clean_doi(doi),
        "url": url,
        "resolved": True,
        "provider": provider,
        "source": {
            "type": provider_key,
            "provider": provider,
            "url": url,
            "doi": clean_doi(doi) or None,
            "retrieved_at": now_iso(),
        },
    }


def dedupe_key(rec: dict[str, Any]) -> str:
    doi = clean_doi(rec.get("doi"))
    if doi:
        return f"doi:{doi.lower()}"
    title = " ".join(str(rec.get("title", "")).lower().split())
    return f"ty:{title}|{rec.get('year') or ''}"
