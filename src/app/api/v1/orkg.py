from __future__ import annotations

import time

import httpx
from fastapi import APIRouter, Query

from ...core.errors import AppError
from ...schemas.orkg import (
    OrkgConnect,
    OrkgConnectResult,
    OrkgSearchResult,
    SparqlQuery,
    SparqlResult,
)
from ...services.orkg.client import ORKGAuthError
from ...services.orkg.sparql import SparqlClient, SparqlGuardError
from ..deps import ApiKeyDep, ORKGDep, SettingsDep

router = APIRouter(prefix="/api/v1/orkg", tags=["orkg"])


@router.post("/connect", response_model=OrkgConnectResult)
async def connect(body: OrkgConnect, orkg: ORKGDep, caller: ApiKeyDep) -> OrkgConnectResult:
    """Authenticate to ORKG (OIDC password grant) and store the token for this user."""
    try:
        token = await orkg.connect(str(caller.user_id), body.username, body.password)
    except ORKGAuthError as exc:
        raise AppError("orkg_auth_failed", str(exc), status=401) from exc
    except httpx.HTTPError as exc:
        raise AppError("orkg_unreachable", f"ORKG unreachable: {exc}", status=502) from exc
    expires_in = max(0, int(token.expires_at - time.time()))
    return OrkgConnectResult(connected=True, expires_in=expires_in)


@router.get("/search", response_model=OrkgSearchResult)
async def search(
    orkg: ORKGDep,
    caller: ApiKeyDep,
    q: str = Query(..., min_length=1),
    size: int = Query(20, ge=1, le=100),
) -> OrkgSearchResult:
    try:
        data = await orkg.search(q, user_key=str(caller.user_id), size=size)
    except httpx.HTTPError as exc:
        raise AppError("orkg_unreachable", f"ORKG search failed: {exc}", status=502) from exc
    items = data.get("content", data if isinstance(data, list) else [])
    if not isinstance(items, list):
        items = []
    total = int(data.get("totalElements", len(items))) if isinstance(data, dict) else len(items)
    return OrkgSearchResult(query=q, total=total, items=items)


@router.post("/sparql", response_model=SparqlResult)
async def sparql(body: SparqlQuery, settings: SettingsDep, caller: ApiKeyDep) -> SparqlResult:
    """Run a guarded, read-only SPARQL query against the ORKG triplestore."""
    client = SparqlClient(
        settings.orkg_sparql_url,
        max_limit=settings.orkg_sparql_max_limit,
        timeout_s=settings.orkg_sparql_timeout_s,
    )
    try:
        return await client.query(body.query, limit=body.limit)
    except SparqlGuardError as exc:
        raise AppError("sparql_rejected", str(exc), status=400) from exc
    except httpx.HTTPError as exc:
        raise AppError("orkg_unreachable", f"SPARQL request failed: {exc}", status=502) from exc
