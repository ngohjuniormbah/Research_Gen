"""Resolve heterogeneous research references into normalized ORKG-backed sources.

The user can paste a mix of ORKG URLs, ORKG ids (R/C/P…), DOIs, and paper titles —
separated by newlines or commas. Each input is classified, resolved against the ORKG
REST API where possible, normalized to a common source record, and tagged with
provenance. Inputs that cannot be resolved are returned separately (never fabricated)."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

from .client import ORKGClient

# ORKG resource ids: R123 (resources/papers/comparisons), plus contribution/predicate ids.
_ORKG_ID_RE = re.compile(r"^(R|C|P|CONTRIBUTION)\d+$", re.IGNORECASE)
_ORKG_URL_ID_RE = re.compile(r"orkg\.org/(?:[a-z]+/)?((?:R|C|P)\d+)", re.IGNORECASE)
# DOI: bare (10.x/…) or as a doi.org URL.
_DOI_RE = re.compile(r"\b(10\.\d{4,9}/[^\s,]+)\b", re.IGNORECASE)


def _now() -> str:
    return datetime.now(UTC).isoformat()


def classify_input(raw: str) -> tuple[str, str]:
    """Return (kind, value): kind in {"orkg_id","doi","title"}."""
    s = raw.strip()
    m = _ORKG_URL_ID_RE.search(s)
    if m:
        return "orkg_id", m.group(1)
    if _ORKG_ID_RE.match(s):
        return "orkg_id", s
    low = s.lower()
    if "doi.org/" in low:  # a DOI URL: take the path after the host as the DOI
        return "doi", s.split("doi.org/", 1)[1].strip()
    m = _DOI_RE.search(s)
    if m and (low.startswith("10.") or "doi" in low):
        return "doi", m.group(1)
    return "title", s


def _is_structured(part: str) -> bool:
    kind, _ = classify_input(part)
    return kind in ("orkg_id", "doi")


def split_inputs(text: str) -> list[str]:
    """Split pasted text into individual references. Commas only split a line when every
    comma-part looks structured (id/DOI/URL) — so titles containing commas stay intact."""
    out: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = [p.strip() for p in line.split(",") if p.strip()]
        if len(parts) > 1 and all(_is_structured(p) for p in parts):
            out.extend(parts)
        else:
            out.append(line)
    # de-duplicate, preserve order
    seen: set[str] = set()
    uniq: list[str] = []
    for item in out:
        if item.lower() not in seen:
            seen.add(item.lower())
            uniq.append(item)
    return uniq


def _normalize_resource(res: dict[str, Any], *, input_value: str) -> dict[str, Any]:
    rid = res.get("id") or res.get("resource_id")
    return {
        "title": str(res.get("title") or res.get("label") or "").strip(),
        "abstract": str(res.get("abstract") or res.get("description") or "").strip(),
        "doi": str(res.get("doi") or "").strip(),
        "year": res.get("year") or res.get("publication_year"),
        "orkg_id": rid,
        "classes": res.get("classes") or [],
        "resolved": True,
        "input": input_value,
        "source": {
            "type": "orkg",
            "resource_id": rid,
            "url": f"https://orkg.org/resource/{rid}" if rid else None,
            "doi": str(res.get("doi") or "").strip() or None,
            "retrieved_at": _now(),
        },
    }


async def _search_first(
    client: ORKGClient, queries: list[str], user_key: str | None
) -> dict[str, Any] | None:
    """Try each query variant against ORKG search; return the first resource found."""
    for q in queries:
        if not q:
            continue
        try:
            data = await client.search(q, user_key=user_key, size=1)
        except Exception:  # noqa: BLE001
            continue
        items = data.get("content", data if isinstance(data, list) else [])
        if isinstance(items, list) and items and isinstance(items[0], dict):
            return items[0]
    return None


async def resolve_one(
    raw: str, *, client: ORKGClient, user_key: str | None = None
) -> dict[str, Any]:
    kind, value = classify_input(raw)
    try:
        if kind == "orkg_id":
            res = await client.get_resource(value, user_key=user_key)
            return _normalize_resource(res, input_value=raw)
        if kind == "doi":
            # A DOI may be indexed on ORKG under the full DOI or just its suffix; try both.
            suffix = value.rsplit("/", 1)[-1]
            hit = await _search_first(client, [value, f'"{value}"', suffix], user_key)
            if hit:
                return _normalize_resource(hit, input_value=raw)
        else:  # title / free text
            hit = await _search_first(client, [value], user_key)
            if hit:
                return _normalize_resource(hit, input_value=raw)
    except Exception:  # noqa: BLE001 - unresolved is a valid, reported outcome
        pass
    # Unresolved: keep the input + what we detected, but never fabricate metadata.
    return {
        "title": raw if kind == "title" else "",
        "doi": value if kind == "doi" else "",
        "orkg_id": value if kind == "orkg_id" else None,
        "resolved": False,
        "input": raw,
        "source": {"type": kind, "url": None, "retrieved_at": _now()},
    }


async def resolve_many(
    text: str, *, client: ORKGClient, user_key: str | None = None
) -> tuple[list[dict[str, Any]], list[str]]:
    """Resolve all references. Returns (resolved_records, unresolved_inputs)."""
    resolved: list[dict[str, Any]] = []
    unresolved: list[str] = []
    for raw in split_inputs(text):
        rec = await resolve_one(raw, client=client, user_key=user_key)
        if rec.get("resolved"):
            resolved.append(rec)
        else:
            resolved.append(rec)  # still return it (marked unresolved) for transparency
            unresolved.append(raw)
    return resolved, unresolved
