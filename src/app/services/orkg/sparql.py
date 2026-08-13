"""Guarded SPARQL client for the ORKG triplestore.

Guardrails (all enforced before a query ever leaves the process):
  * only read forms are allowed: SELECT / CONSTRUCT / ASK / DESCRIBE
  * a LIMIT is injected when a SELECT/DESCRIBE query has none
  * a hard request timeout bounds every call
"""

from __future__ import annotations

import re
from typing import Any

import httpx

from ...schemas.orkg import SparqlResult

_COMMENT_RE = re.compile(r"(?m)#.*$")
_ALLOWED = ("select", "construct", "ask", "describe")
_LIMIT_RE = re.compile(r"\blimit\s+\d+\b", re.IGNORECASE)
# Reject anything that looks like an update/mutation form.
_FORBIDDEN = re.compile(
    r"\b(insert|delete|drop|clear|create|load|move|copy|add|with|"
    r"service)\b",
    re.IGNORECASE,
)


class SparqlGuardError(ValueError):
    """Raised when a query violates the read-only guardrails."""


def _strip(query: str) -> str:
    return _COMMENT_RE.sub("", query).strip()


def guard_query(query: str, *, max_limit: int) -> str:
    """Validate a query is read-only and ensure it carries a bounded LIMIT.

    Returns the (possibly LIMIT-augmented) query. Raises SparqlGuardError otherwise."""
    stripped = _strip(query)
    if not stripped:
        raise SparqlGuardError("empty query")

    body = re.sub(r"(?is)^\s*(prefix\s+\S+\s*:\s*<[^>]*>\s*)+", "", stripped)
    first = body.lower().lstrip()
    keyword = next((k for k in _ALLOWED if first.startswith(k)), None)
    if keyword is None:
        raise SparqlGuardError(
            "only SELECT, CONSTRUCT, ASK or DESCRIBE queries are allowed"
        )

    if _FORBIDDEN.search(stripped):
        raise SparqlGuardError("query contains a forbidden (mutating) keyword")

    if ";" in stripped.rstrip(";"):
        raise SparqlGuardError("multiple statements are not allowed")

    # ASK returns a boolean; LIMIT is meaningless there.
    if keyword in ("select", "describe", "construct") and not _LIMIT_RE.search(stripped):
        stripped = f"{stripped.rstrip()}\nLIMIT {max_limit}"
    else:
        stripped = _clamp_limit(stripped, max_limit)
    return stripped


def _clamp_limit(query: str, max_limit: int) -> str:
    def _cap(match: re.Match[str]) -> str:
        value = int(re.search(r"\d+", match.group(0)).group(0))  # type: ignore[union-attr]
        return f"LIMIT {min(value, max_limit)}"

    return _LIMIT_RE.sub(_cap, query)


def _parse_results(data: dict[str, Any]) -> SparqlResult:
    columns = data.get("head", {}).get("vars", [])
    rows: list[dict[str, Any]] = []
    for binding in data.get("results", {}).get("bindings", []):
        rows.append({col: binding.get(col, {}).get("value") for col in columns})
    return SparqlResult(columns=columns, rows=rows, raw=data)


class SparqlClient:
    def __init__(self, endpoint: str, *, max_limit: int = 500, timeout_s: float = 30.0) -> None:
        self._endpoint = endpoint
        self._max_limit = max_limit
        self._timeout = timeout_s

    async def query(self, sparql: str, *, limit: int | None = None) -> SparqlResult:
        cap = min(limit, self._max_limit) if limit else self._max_limit
        guarded = guard_query(sparql, max_limit=cap)
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(
                self._endpoint,
                data={"query": guarded},
                headers={"Accept": "application/sparql-results+json"},
            )
        resp.raise_for_status()
        # ASK responses also come back as JSON with a "boolean" field.
        return _parse_results(resp.json())
