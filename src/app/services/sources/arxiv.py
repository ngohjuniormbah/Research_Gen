"""arXiv connector (http://export.arxiv.org/api) — open-access preprints in physics, CS,
math, quantitative biology, etc. Keyless. Returns Atom XML, parsed here."""

from __future__ import annotations

from typing import Any
from xml.etree import ElementTree as ET

from .base import fetch_text, record

PROVIDER = "arXiv"
KEY = "arxiv"
_URL = "http://export.arxiv.org/api/query"
_ATOM = "{http://www.w3.org/2005/Atom}"


async def search(query: str, *, size: int = 10) -> list[dict[str, Any]]:
    xml = await fetch_text(
        _URL, {"search_query": f"all:{query}", "max_results": min(size, 25)}
    )
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        return []
    out: list[dict[str, Any]] = []
    for entry in root.findall(f"{_ATOM}entry"):
        title = (entry.findtext(f"{_ATOM}title") or "").strip()
        summary = (entry.findtext(f"{_ATOM}summary") or "").strip()
        url = (entry.findtext(f"{_ATOM}id") or "").strip()
        published = entry.findtext(f"{_ATOM}published") or ""
        year = int(published[:4]) if published[:4].isdigit() else None
        authors = [
            (a.findtext(f"{_ATOM}name") or "").strip()
            for a in entry.findall(f"{_ATOM}author")
        ]
        doi = (entry.findtext("{http://arxiv.org/schemas/atom}doi") or "").strip()
        out.append(
            record(
                title=" ".join(title.split()),
                provider=PROVIDER,
                provider_key=KEY,
                url=url,
                abstract=" ".join(summary.split()),
                authors=[a for a in authors if a],
                year=year,
                venue="arXiv",
                doi=doi,
            )
        )
    return out
