"""Crossref connector (https://api.crossref.org) — DOI registration agency covering most
published journal articles. Keyless."""

from __future__ import annotations

import re
from typing import Any

from .base import fetch_json, record

PROVIDER = "Crossref"
KEY = "crossref"
_URL = "https://api.crossref.org/works"
_TAG_RE = re.compile(r"<[^>]+>")


def _first(seq: Any) -> str:
    if isinstance(seq, list) and seq:
        return str(seq[0])
    return str(seq or "")


def _year(item: dict[str, Any]) -> int | None:
    for k in ("published", "published-print", "published-online", "issued"):
        parts = (item.get(k) or {}).get("date-parts") or []
        if parts and parts[0] and isinstance(parts[0][0], int):
            return parts[0][0]
    return None


async def search(query: str, *, size: int = 10) -> list[dict[str, Any]]:
    data = await fetch_json(
        _URL,
        {
            "query": query,
            "rows": min(size, 25),
            "select": "title,DOI,abstract,author,issued,container-title,URL",
        },
    )
    out: list[dict[str, Any]] = []
    for item in (data.get("message") or {}).get("items", []) or []:
        authors = [
            " ".join(x for x in [a.get("given"), a.get("family")] if x)
            for a in (item.get("author") or [])
        ]
        abstract = _TAG_RE.sub("", item.get("abstract") or "").strip()
        out.append(
            record(
                title=_first(item.get("title")),
                provider=PROVIDER,
                provider_key=KEY,
                url=item.get("URL"),
                abstract=abstract,
                authors=[a for a in authors if a],
                year=_year(item),
                venue=_first(item.get("container-title")),
                doi=item.get("DOI") or "",
            )
        )
    return out
