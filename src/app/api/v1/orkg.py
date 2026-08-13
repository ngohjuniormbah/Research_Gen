from __future__ import annotations

import time

import httpx
from fastapi import APIRouter, Query

from ...core.errors import AppError, ErrorCode
from ...schemas.orkg import (
    OrkgConnect,
    OrkgConnectResult,
    OrkgSearchResult,
    SparqlQuery,
    SparqlResult,
)
from ...services.orkg.client import ORKGAuthError
from ...services.orkg.sparql import SparqlClient, SparqlGuardError
from ..deps import ORKGDep, RateLimitedKeyDep, SettingsDep, SparqlRateLimitedKeyDep

router = APIRouter(prefix="/api/v1/orkg", tags=["orkg"])


@router.post(
    "/connect",
    response_model=OrkgConnectResult,
    summary="Connect to ORKG (OIDC)",
    description="Authenticate to ORKG via the OIDC password grant. The resulting token "
    "is stored **encrypted at rest** and refreshed automatically.",
)
async def connect(
    body: OrkgConnect, orkg: ORKGDep, caller: RateLimitedKeyDep
) -> OrkgConnectResult:
    try:
        token = await orkg.connect(str(caller.user_id), body.username, body.password)
    except ORKGAuthError as exc:
        raise AppError(ErrorCode.ORKG_AUTH_FAILED, str(exc), status=401) from exc
    except httpx.HTTPError as exc:
        raise AppError(
            ErrorCode.UPSTREAM_UNAVAILABLE, f"ORKG unreachable: {exc}", status=502
        ) from exc
    expires_in = max(0, int(token.expires_at - time.time()))
    return OrkgConnectResult(connected=True, expires_in=expires_in)


@router.get(
    "/search",
    response_model=OrkgSearchResult,
    summary="Search ORKG resources",
)
async def search(
    orkg: ORKGDep,
    caller: RateLimitedKeyDep,
    q: str = Query(..., min_length=1, examples=["knowledge graphs"]),
    size: int = Query(20, ge=1, le=100),
) -> OrkgSearchResult:
    try:
        data = await orkg.search(q, user_key=str(caller.user_id), size=size)
    except httpx.HTTPError as exc:
        raise AppError(
            ErrorCode.UPSTREAM_UNAVAILABLE, f"ORKG search failed: {exc}", status=502
        ) from exc
    items = data.get("content", data if isinstance(data, list) else [])
    if not isinstance(items, list):
        items = []
    total = int(data.get("totalElements", len(items))) if isinstance(data, dict) else len(items)
    return OrkgSearchResult(query=q, total=total, items=items)


@router.post(
    "/sparql",
    response_model=SparqlResult,
    summary="Run a guarded SPARQL query",
    description="Read-only SPARQL against the ORKG triplestore. Only "
    "SELECT/CONSTRUCT/ASK/DESCRIBE are allowed, a LIMIT is injected if absent, and a "
    "hard timeout applies. Subject to a stricter per-minute rate limit.",
)
async def sparql(
    body: SparqlQuery, settings: SettingsDep, caller: SparqlRateLimitedKeyDep
) -> SparqlResult:
    client = SparqlClient(
        settings.orkg_sparql_url,
        max_limit=settings.orkg_sparql_max_limit,
        timeout_s=settings.orkg_sparql_timeout_s,
    )
    try:
        return await client.query(body.query, limit=body.limit)
    except SparqlGuardError as exc:
        raise AppError(ErrorCode.SPARQL_REJECTED, str(exc), status=400) from exc
    except httpx.HTTPError as exc:
        raise AppError(
            ErrorCode.UPSTREAM_UNAVAILABLE, f"SPARQL request failed: {exc}", status=502
        ) from exc
