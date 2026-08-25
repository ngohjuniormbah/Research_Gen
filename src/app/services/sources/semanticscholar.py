"""Semantic Scholar connector (https://api.semanticscholar.org) — a large AI-focused
scholarly index. Keyless (rate-limited)."""

from __future__ import annotations

from typing import Any

from .base import fetch_json, record

PROVIDER = "Semantic Scholar"
KEY = "semanticscholar"
_URL = "https://api.semanticscholar.org/graph/v1/paper/search"


async def search(query: str, *, size: int = 10) -> list[dict[str, Any]]:
    data = await fetch_json(
        _URL,
        {
            "query": query,
            "limit": min(size, 25),
            "fields": "title,abstract,year,authors,externalIds,venue,url",
        },
    )
    out: list[dict[str, Any]] = []
    for p in data.get("data", []) or []:
        authors = [a.get("name", "") for a in (p.get("authors") or []) if a.get("name")]
        doi = (p.get("externalIds") or {}).get("DOI", "") or ""
        out.append(
            record(
                title=p.get("title") or "",
                provider=PROVIDER,
                provider_key=KEY,
                url=p.get("url"),
                abstract=p.get("abstract") or "",
                authors=authors,
                year=p.get("year"),
                venue=p.get("venue") or "",
                doi=doi,
            )
        )
    return out
