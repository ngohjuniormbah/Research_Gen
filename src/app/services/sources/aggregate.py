"""Fan out a query to several real scholarly sources in parallel, then merge and
de-duplicate the results — like a research meta-search. Each surviving record keeps its
provider tag and origin link so the UI can show where every result came from."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from . import arxiv, crossref, openalex
from .base import dedupe_key

# Registry of available connectors. ORKG is handled separately (it has its own auth/client
# and dedicated tab); these are the keyless open-scholarship sources.
Provider = Callable[..., Awaitable[list[dict[str, Any]]]]
PROVIDERS: dict[str, Provider] = {
    openalex.KEY: openalex.search,
    crossref.KEY: crossref.search,
    arxiv.KEY: arxiv.search,
}
DEFAULT_PROVIDERS = list(PROVIDERS.keys())


async def _safe(fn: Provider, query: str, size: int) -> list[dict[str, Any]]:
    try:
        return await fn(query, size=size)
    except Exception:  # noqa: BLE001 - one source failing must not sink the whole search
        return []


async def search_sources(
    query: str, *, providers: list[str] | None = None, size: int = 10
) -> tuple[list[dict[str, Any]], list[str]]:
    """Return (merged_records, providers_used). Records are de-duplicated by DOI/title,
    interleaved so no single source dominates the top of the list."""
    keys = [p for p in (providers or DEFAULT_PROVIDERS) if p in PROVIDERS]
    if not keys:
        keys = DEFAULT_PROVIDERS
    results = await asyncio.gather(*[_safe(PROVIDERS[k], query, size) for k in keys])

    seen: set[str] = set()
    merged: list[dict[str, Any]] = []
    # Round-robin across providers so the first page shows a mix, not 10 from one source.
    for row in range(max((len(r) for r in results), default=0)):
        for res in results:
            if row < len(res):
                rec = res[row]
                key = dedupe_key(rec)
                if key in seen:
                    # Same work from two sources: record the extra provider for transparency.
                    prov = rec.get("provider")
                    for m in merged:
                        if dedupe_key(m) == key:
                            also = m.setdefault("also_in", [])
                            if prov and prov not in also and prov != m.get("provider"):
                                also.append(prov)
                            break
                    continue
                seen.add(key)
                merged.append(rec)
    return merged, keys
