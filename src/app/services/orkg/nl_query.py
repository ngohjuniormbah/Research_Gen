"""Natural-language -> ORKG retrieval.

Turns a researcher's plain-language request into structured ORKG results without the
user ever writing SPARQL. The LLM proposes a query; the BACKEND decides whether it is
safe and executable (via ``guard_query``) and always preserves both the original request
and the generated query for audit. If SPARQL generation/validation/execution does not
yield usable rows, we fall back to ORKG full-text search so the user still gets grounded
results. Every returned record carries provenance (where it came from)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from ..llm.base import ChatMessage, LLMProvider
from .client import ORKGClient
from .sparql import SparqlClient, SparqlGuardError

SPARQL_SYSTEM_PROMPT = (
    "You translate a researcher's natural-language request into ONE read-only SPARQL "
    "query for the ORKG triplestore. Rules: use only SELECT; never use INSERT/DELETE/"
    "DROP/CLEAR/LOAD/CREATE or SERVICE; return ONLY the SPARQL query with no prose and "
    "no markdown fences; always include a LIMIT. If you cannot express the request as a "
    "safe SPARQL SELECT, return the single word: NONE."
)

_FENCE_RE = re.compile(r"^```(?:sparql)?\s*|\s*```$", re.IGNORECASE | re.MULTILINE)


def _now() -> str:
    return datetime.now(UTC).isoformat()


@dataclass
class OrkgRetrieval:
    """Result of an NL ORKG retrieval, with full audit trail."""
    request: str
    mode: str  # "sparql" | "search"
    records: list[dict[str, Any]]
    count: int
    sparql: str | None = None          # the validated query that ran (audit)
    sparql_error: str | None = None    # why SPARQL was skipped, if it was
    columns: list[str] = field(default_factory=list)


async def generate_sparql(provider: LLMProvider, request: str) -> str:
    """Ask the LLM for a candidate SPARQL query. Returns "" if it declined."""
    out = await provider.generate(
        [
            ChatMessage(role="system", content=SPARQL_SYSTEM_PROMPT),
            ChatMessage(role="user", content=request),
        ],
        max_tokens=400,
    )
    cleaned = _FENCE_RE.sub("", out).strip()
    if not cleaned or cleaned.strip().upper() == "NONE":
        return ""
    return cleaned


def _sparql_rows_to_records(columns: list[str], rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for row in rows:
        # Best-effort: surface an ORKG resource id/url if any binding looks like one.
        resource_id = None
        url = None
        for val in row.values():
            if isinstance(val, str) and "orkg.org" in val:
                url = val
                m = re.search(r"/(R\d+|C\d+|P\d+)\b", val)
                if m:
                    resource_id = m.group(1)
        records.append({
            **row,
            "source": {
                "type": "orkg-sparql",
                "resource_id": resource_id,
                "url": url,
                "retrieved_at": _now(),
            },
        })
    return records


def _orkg_item_to_record(item: dict[str, Any]) -> dict[str, Any]:
    rid = item.get("id")
    return {
        "title": str(item.get("title") or item.get("label") or "").strip(),
        "abstract": str(item.get("abstract") or item.get("description") or "").strip(),
        "doi": str(item.get("doi") or "").strip(),
        "year": item.get("year") or item.get("publication_year"),
        "orkg_id": rid,
        "source": {
            "type": "orkg",
            "resource_id": rid,
            "url": f"https://orkg.org/resource/{rid}" if rid else None,
            "doi": str(item.get("doi") or "").strip() or None,
            "retrieved_at": _now(),
        },
    }


async def ask_orkg(
    *,
    request: str,
    provider: LLMProvider,
    client: ORKGClient,
    sparql_client: SparqlClient | None,
    user_key: str | None = None,
    size: int = 20,
) -> OrkgRetrieval:
    """NL -> (SPARQL, validated, executed) or fall back to ORKG search. Always grounded."""
    request = request.strip()
    sparql_error: str | None = None
    validated: str | None = None

    if sparql_client is not None:
        try:
            candidate = await generate_sparql(provider, request)
            if candidate:
                # The BACKEND validates — never trust the raw LLM query.
                result = await sparql_client.query(candidate, limit=size)
                validated = candidate
                if result.rows:
                    records = _sparql_rows_to_records(result.columns, result.rows)
                    return OrkgRetrieval(
                        request=request, mode="sparql", records=records,
                        count=len(records), sparql=validated, columns=result.columns,
                    )
                sparql_error = "query executed but returned no rows; used search instead"
            else:
                sparql_error = "no SPARQL could be generated; used search instead"
        except SparqlGuardError as exc:
            sparql_error = f"generated query rejected by safety guard: {exc}"
        except Exception as exc:  # noqa: BLE001 - fall back to search, but record why
            sparql_error = f"SPARQL execution failed: {exc}"[:200]

    data = await client.search(request, user_key=user_key, size=size)
    items = data.get("content", data if isinstance(data, list) else [])
    if not isinstance(items, list):
        items = []
    records = [_orkg_item_to_record(i) for i in items if isinstance(i, dict)]
    return OrkgRetrieval(
        request=request, mode="search", records=records, count=len(records),
        sparql=validated, sparql_error=sparql_error,
    )
