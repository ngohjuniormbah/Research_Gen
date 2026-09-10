"""Resolve heterogeneous research references into normalized ORKG-backed sources.

Supports ORKG comparison tables with 48+ contributions, fetching properties concurrently
and expanding them into individual citable source records without data loss.
"""

from __future__ import annotations

import asyncio
import re
from datetime import UTC, datetime
from typing import Any

from .client import ORKGClient

# ORKG resource identifiers: supports standard (R1234), alphanumeric, and named comparison slugs
_ORKG_ID_RE = re.compile(
    r"^(R|C|P|CONTRIBUTION)[_\d][A-Za-z0-9_-]*$", re.IGNORECASE)
_ORKG_URL_ID_RE = re.compile(
    r"orkg\.org/(?:[a-z0-9_-]+/)+([A-Za-z0-9_-]+)/?(?:\?.*)?$", re.IGNORECASE)
_DOI_RE = re.compile(r"\b(10\.\d{4,9}/[^\s,]+)\b", re.IGNORECASE)

# Scaled limits to support matrices with 48+ comparison papers
_MAX_CONTRIBS = 120
_MAX_PROPS = 1000
_MAX_STRUCTURED_CHARS = 120000


def _now() -> str:
    return datetime.now(UTC).isoformat()


def classify_input(raw: str) -> tuple[str, str]:
    """Return (kind, value): kind in {"orkg_id", "doi", "title"}."""
    s = raw.strip()
    m = _ORKG_URL_ID_RE.search(s)
    if m:
        return "orkg_id", m.group(1)
    if _ORKG_ID_RE.match(s):
        return "orkg_id", s
    low = s.lower()
    if "doi.org/" in low:
        return "doi", s.split("doi.org/", 1)[1].strip()
    m = _DOI_RE.search(s)
    if m and (low.startswith("10.") or "doi" in low):
        return "doi", m.group(1)
    return "title", s


def _is_structured(part: str) -> bool:
    kind, _ = classify_input(part)
    return kind in ("orkg_id", "doi")


def split_inputs(text: str) -> list[str]:
    """Split pasted text into individual references."""
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


async def _statement_props(
    client: ORKGClient, subject_id: str, user_key: str | None
) -> list[tuple[str, str, str | None, str]]:
    """Return (predicate_label, object_label, object_id, object_class) for a subject."""
    out: list[tuple[str, str, str | None, str]] = []
    stmts = await client.get_statements(subject_id, user_key=user_key)
    for s in stmts:
        pred = s.get("predicate") or {}
        obj = s.get("object") or {}
        plabel = str(pred.get("label") or pred.get("id") or "").strip()
        olabel = str(obj.get("label") or obj.get("value") or "").strip()
        oid = obj.get("id")
        oclass = str(obj.get("_class") or obj.get("class") or "").strip()
        out.append((plabel, olabel, oid, oclass))
    return out


async def _build_structured(
    client: ORKGClient, resource_id: str, user_key: str | None
) -> tuple[str, list[dict[str, Any]]]:
    """Reconstruct a comparison table's structured properties and unpack child contributions."""
    lines: list[str] = []
    unpacked_records: list[dict[str, Any]] = []

    top = await _statement_props(client, resource_id, user_key)
    direct: list[str] = []
    contribs: list[tuple[str, str]] = []

    for plabel, olabel, oid, oclass in top:
        is_contrib = "contribution" in plabel.lower() or "contribution" in olabel.lower()
        if oid and oclass == "resource" and is_contrib:
            contribs.append((olabel or str(oid), str(oid)))
        elif plabel and olabel:
            direct.append(f"- {plabel}: {olabel}")

    if direct:
        lines.append("Properties:")
        lines.extend(direct[:_MAX_PROPS])

    # Fetch all comparison contributions concurrently to eliminate latency
    async def _fetch_one_contrib(name: str, cid: str) -> tuple[str, str, list[tuple[str, str, str | None, str]]]:
        sub = await _statement_props(client, cid, user_key)
        return name, cid, sub

    target_contribs = contribs[:_MAX_CONTRIBS]
    if target_contribs:
        results = await asyncio.gather(
            *[_fetch_one_contrib(name, cid) for name, cid in target_contribs],
            return_exceptions=True,
        )

        for res in results:
            if isinstance(res, Exception):
                continue
            name, cid, sub = res
            sub_lines = [f"    - {p}: {o}" for p, o,
                         _oid, _oc in sub if p and o][:_MAX_PROPS]
            if sub_lines:
                lines.append(f"Contribution — {name} ({cid}):")
                lines.extend(sub_lines)

                # Extract metadata if present
                sub_doi = next(
                    (o for p, o, _, _ in sub if "doi" in p.lower()), "")
                sub_year_raw = next(
                    (o for p, o, _, _ in sub if "year" in p.lower() or "date" in p.lower()), None)
                sub_year = None
                if sub_year_raw:
                    m = re.search(r"(19\d{2}|20\d{2})", str(sub_year_raw))
                    if m:
                        sub_year = int(m.group(1))

                # Create an unpacked SourceRecord so this comparison paper gets its own [n] citation
                unpacked_records.append({
                    "title": str(name),
                    "abstract": f"Extracted from ORKG Comparison {resource_id}:\n" + "\n".join(f"- {p}: {o}" for p, o, _, _ in sub if p and o),
                    "doi": sub_doi or "",
                    "year": sub_year,
                    "orkg_id": cid,
                    "resolved": True,
                    "input": f"orkg:{cid}",
                    "source": {
                        "type": "orkg-comparison-item",
                        "comparison_id": resource_id,
                        "resource_id": cid,
                        "url": f"https://orkg.org/resource/{cid}",
                        "retrieved_at": _now(),
                    },
                })

    structured_text = "\n".join(lines)[:_MAX_STRUCTURED_CHARS]
    return structured_text, unpacked_records


async def _safe_structured(
    client: ORKGClient, resource_id: str, user_key: str | None
) -> tuple[str, list[dict[str, Any]]]:
    try:
        return await _build_structured(client, resource_id, user_key)
    except Exception:
        return "", []


async def _search_first(
    client: ORKGClient, queries: list[str], user_key: str | None
) -> dict[str, Any] | None:
    for q in queries:
        if not q:
            continue
        try:
            data = await client.search(q, user_key=user_key, size=1)
        except Exception:
            continue
        items = data.get("content", data if isinstance(data, list) else [])
        if isinstance(items, list) and items and isinstance(items[0], dict):
            return items[0]
    return None


async def _enrich(
    client: ORKGClient, rec: dict[str, Any], user_key: str | None
) -> dict[str, Any]:
    rid = rec.get("orkg_id")
    if not rid:
        return rec
    structured_text, unpacked_records = await _safe_structured(client, str(rid), user_key)
    if structured_text:
        rec["structured"] = structured_text
        base = str(rec.get("abstract") or "").strip()
        rec["abstract"] = f"{base}\n\n{structured_text}".strip(
        ) if base else structured_text
    if unpacked_records:
        rec["unpacked_records"] = unpacked_records
    return rec


async def resolve_one(
    raw: str, *, client: ORKGClient, user_key: str | None = None
) -> dict[str, Any]:
    kind, value = classify_input(raw)
    try:
        if kind == "orkg_id":
            res = None
            try:
                res = await client.get_resource(value, user_key=user_key)
            except Exception:
                # Fallback to the dedicated comparisons endpoint if /resources/ 404s
                if hasattr(client, "get_comparison"):
                    try:
                        res = await client.get_comparison(value, user_key=user_key)
                    except Exception:
                        pass
            if res:
                return await _enrich(client, _normalize_resource(res, input_value=raw), user_key)

        if kind == "doi":
            suffix = value.rsplit("/", 1)[-1]
            hit = await _search_first(client, [value, f'"{value}"', suffix], user_key)
            if hit:
                return await _enrich(client, _normalize_resource(hit, input_value=raw), user_key)
        else:
            hit = await _search_first(client, [value], user_key)
            if hit:
                return await _enrich(client, _normalize_resource(hit, input_value=raw), user_key)
    except Exception:
        pass

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
    """Resolve all references and unpack comparison tables into discrete citable sources."""
    resolved: list[dict[str, Any]] = []
    unresolved: list[str] = []

    for raw in split_inputs(text):
        rec = await resolve_one(raw, client=client, user_key=user_key)
        if rec.get("resolved"):
            resolved.append(rec)
            unpacked = rec.get("unpacked_records") or []
            if unpacked:
                resolved.extend(unpacked)
        else:
            resolved.append(rec)
            unresolved.append(raw)

    return resolved, unresolved
