from __future__ import annotations

from fastapi import APIRouter, Query

from ...schemas.sources import SourcesSearchResult
from ...services.sources import DEFAULT_PROVIDERS, search_sources
from ..deps import RateLimitedKeyDep

router = APIRouter(prefix="/api/v1/sources", tags=["sources"])


@router.get(
    "/search",
    response_model=SourcesSearchResult,
    summary="Search multiple real scholarly sources at once",
    description="Meta-search across open scholarly APIs (OpenAlex, Crossref, arXiv) in "
    "parallel. Results are normalized, de-duplicated across sources, and each record is "
    "tagged with its provider and origin link (provenance). Never fabricated — a source "
    "that fails or returns nothing is simply omitted.",
)
async def search(
    caller: RateLimitedKeyDep,
    q: str = Query(..., min_length=1, examples=["machine learning for malaria detection"]),
    size: int = Query(10, ge=1, le=25),
    providers: str | None = Query(
        None,
        description="Comma-separated provider keys to include "
        f"(default: {','.join(DEFAULT_PROVIDERS)}).",
    ),
) -> SourcesSearchResult:
    keys = [p.strip() for p in providers.split(",") if p.strip()] if providers else None
    records, used = await search_sources(q, providers=keys, size=size)
    return SourcesSearchResult(query=q, count=len(records), providers=used, records=records)
