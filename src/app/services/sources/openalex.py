"""OpenAlex connector (https://api.openalex.org) — a large, open catalog of scholarly
works. Keyless. Abstracts come back as an inverted index and are reconstructed here."""

from __future__ import annotations

from typing import Any

from .base import fetch_json, record

PROVIDER = "OpenAlex"
KEY = "openalex"
_URL = "https://api.openalex.org/works"


def _abstract_from_inverted(index: dict[str, list[int]] | None) -> str:
    if not index:
        return ""
    positions: list[tuple[int, str]] = []
    for word, idxs in index.items():
        for i in idxs:
            positions.append((i, word))
    positions.sort(key=lambda p: p[0])
    return " ".join(w for _i, w in positions)


async def search(query: str, *, size: int = 10) -> list[dict[str, Any]]:
    data = await fetch_json(
        _URL,
        {
            "search": query,
            "per_page": min(size, 25),
            "mailto": "research@worldmodelofscience.app",
        },
    )
    out: list[dict[str, Any]] = []
    for w in data.get("results", []) or []:
        authors = [
            a.get("author", {}).get("display_name", "")
            for a in (w.get("authorships") or [])
            if a.get("author")
        ]
        venue = (
            (w.get("primary_location") or {}).get("source", {}) or {}
        ).get("display_name", "") or ""
        out.append(
            record(
                title=w.get("title") or w.get("display_name") or "",
                provider=PROVIDER,
                provider_key=KEY,
                url=w.get("id"),
                abstract=_abstract_from_inverted(w.get("abstract_inverted_index")),
                authors=[a for a in authors if a],
                year=w.get("publication_year"),
                venue=venue,
                doi=w.get("doi") or "",
            )
        )
    return out
