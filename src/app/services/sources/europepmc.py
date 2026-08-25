"""Europe PMC connector (https://www.ebi.ac.uk/europepmc) — life-sciences and biomedical
literature (PubMed, PMC, preprints). Keyless."""

from __future__ import annotations

from typing import Any

from .base import fetch_json, record

PROVIDER = "Europe PMC"
KEY = "europepmc"
_URL = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"


async def search(query: str, *, size: int = 10) -> list[dict[str, Any]]:
    data = await fetch_json(
        _URL,
        {"query": query, "format": "json", "resultType": "core", "pageSize": min(size, 25)},
    )
    results = ((data.get("resultList") or {}).get("result")) or []
    out: list[dict[str, Any]] = []
    for r in results:
        author_string = r.get("authorString") or ""
        authors = [a.strip() for a in author_string.split(",") if a.strip()]
        year = None
        if str(r.get("pubYear") or "").isdigit():
            year = int(r["pubYear"])
        out.append(
            record(
                title=r.get("title") or "",
                provider=PROVIDER,
                provider_key=KEY,
                url=(f"https://europepmc.org/article/{r.get('source')}/{r.get('id')}"
                     if r.get("source") and r.get("id") else None),
                abstract=r.get("abstractText") or "",
                authors=authors,
                year=year,
                venue=r.get("journalTitle") or "",
                doi=r.get("doi") or "",
            )
        )
    return out
