"""File ingestion. Every parser emits the same canonical ``SourceRecord`` list so the
rest of the pipeline never learns what the upload originally was."""

from __future__ import annotations

import io
import json
import re
from typing import Any

import pandas as pd

from ...schemas.source_record import SourceRecord

SUPPORTED = ("csv", "xlsx", "pdf", "json")


class ParseError(Exception):
    """Raised when an upload cannot be parsed into SourceRecords."""


# Canonical field -> accepted column/key aliases (all matched case-insensitively).
# Includes schema.org / Dublin Core terms so JSON-LD graph nodes map cleanly.
_ALIASES: dict[str, tuple[str, ...]] = {
    "title": ("title", "name", "headline", "label", "paper_title", "article_title"),
    "abstract": ("abstract", "summary", "description"),
    "authors": ("authors", "author", "author_names", "creators", "creator", "contributor"),
    "year": (
        "year", "publication_year", "publicationyear", "pub_year", "date", "published",
        "datepublished", "date_published", "datecreated", "issued",
    ),
    "venue": (
        "venue", "journal", "conference", "publisher", "source", "booktitle",
        "ispartof", "container_title", "containertitle",
    ),
    "doi": ("doi", "digital_object_identifier"),
    "full_text": ("full_text", "fulltext", "text", "body", "content"),
}


def detect_kind(filename: str, content_type: str = "") -> str:
    name = (filename or "").lower()
    ct = (content_type or "").lower()
    if name.endswith(".csv") or "csv" in ct:
        return "csv"
    if name.endswith((".xlsx", ".xls")) or "spreadsheet" in ct or "excel" in ct:
        return "xlsx"
    if name.endswith(".pdf") or "pdf" in ct:
        return "pdf"
    if name.endswith(".json") or "json" in ct:
        return "json"
    raise ParseError(f"unsupported file type: filename={filename!r} content_type={ct!r}")


def sniff_kind(data: bytes, filename: str = "", content_type: str = "") -> str:
    """Determine the file kind from MAGIC BYTES, not just the extension.

    Binary formats are identified by signature; text formats (csv/json) are confirmed by
    decoding and shape. The extension only breaks ties, never overrides the bytes."""
    if not data:
        raise ParseError("empty file")

    # Binary signatures win outright.
    if data[:5] == b"%PDF-" or data[:4] == b"%PDF":
        return "pdf"
    if data[:4] == b"PK\x03\x04":
        # OOXML/zip container. We only accept xlsx among zip-based uploads.
        name = (filename or "").lower()
        if name.endswith((".xlsx", ".xlsm", ".xls")) or "sheet" in content_type.lower():
            return "xlsx"
        raise ParseError("zip-based upload is not a supported spreadsheet (.xlsx)")

    # Text formats: must decode as UTF-8.
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ParseError("file is not valid UTF-8 text or a supported binary format") from exc

    stripped = text.lstrip()
    name = (filename or "").lower()
    if stripped[:1] in ("{", "["):
        return "json"
    if name.endswith(".json") or "json" in content_type.lower():
        return "json"
    if name.endswith(".csv") or "csv" in content_type.lower() or ("," in text or "\n" in text):
        return "csv"
    raise ParseError("could not identify a supported file type from its contents")


def parse_bytes(data: bytes, filename: str, content_type: str = "") -> list[SourceRecord]:
    kind = sniff_kind(data, filename, content_type)
    if kind == "csv":
        return _parse_tabular(pd.read_csv(io.BytesIO(data)))
    if kind == "xlsx":
        return _parse_tabular(pd.read_excel(io.BytesIO(data)))
    if kind == "json":
        return _parse_json(data)
    if kind == "pdf":
        return _parse_pdf(data)
    raise ParseError(f"unsupported file type: {kind}")  # pragma: no cover


# --------------------------------------------------------------------------- #
# helpers                                                                      #
# --------------------------------------------------------------------------- #
def _norm_key(key: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(key).strip().lower()).strip("_")


def _pick(row: dict[str, Any], field: str) -> Any:
    normalized = {_norm_key(k): v for k, v in row.items()}
    for alias in _ALIASES[field]:
        if alias in normalized and _present(normalized[alias]):
            return normalized[alias]
    return None


def _present(value: Any) -> bool:
    if value is None:
        return False
    try:
        if pd.isna(value):  # type: ignore[arg-type]
            return False
    except (TypeError, ValueError):
        pass
    return str(value).strip() != ""


def _to_authors(value: Any) -> list[str]:
    if value is None or not _present(value):
        return []
    if isinstance(value, (list, tuple)):
        return [str(v).strip() for v in value if str(v).strip()]
    text = str(value)
    # If semicolons are present, they separate authors and any comma is intra-name
    # ("Last, First"). Otherwise commas separate authors.
    if ";" in text:
        pattern = r"\s*(?:;|\||\band\b)\s*"
    else:
        pattern = r"\s*(?:,|\||\band\b)\s*"
    parts = re.split(pattern, text)
    return [p.strip() for p in parts if p.strip()]


def _to_year(value: Any) -> int | None:
    if not _present(value):
        return None
    match = re.search(r"(1[5-9]\d{2}|20\d{2}|21\d{2})", str(value))
    return int(match.group(1)) if match else None


def _record_from_mapping(row: dict[str, Any]) -> SourceRecord:
    return SourceRecord(
        title=str(_pick(row, "title") or "").strip(),
        abstract=str(_pick(row, "abstract") or "").strip(),
        authors=_to_authors(_pick(row, "authors")),
        year=_to_year(_pick(row, "year")),
        venue=str(_pick(row, "venue") or "").strip(),
        doi=str(_pick(row, "doi") or "").strip(),
        full_text=(str(_pick(row, "full_text")).strip() if _pick(row, "full_text") else None),
        raw={k: _jsonable(v) for k, v in row.items()},
    )


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool, list, dict)):
        return value
    if not _present(value):
        return None
    return str(value)


def _parse_tabular(df: pd.DataFrame) -> list[SourceRecord]:
    records = [_record_from_mapping(row) for row in df.to_dict(orient="records")]
    if not records:
        raise ParseError("no rows found in tabular file")
    return records


def _parse_json(data: bytes) -> list[SourceRecord]:
    try:
        payload = json.loads(data.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ParseError(f"invalid JSON: {exc}") from exc

    if _is_jsonld(payload):
        return _parse_jsonld(payload)

    rows: Any = payload
    if isinstance(payload, dict):
        for key in ("records", "items", "results", "data", "papers"):
            if isinstance(payload.get(key), list):
                rows = payload[key]
                break
        else:
            rows = [payload]
    if not isinstance(rows, list):
        raise ParseError("JSON must be a list of objects or an object wrapping one")
    records = [_record_from_mapping(r) for r in rows if isinstance(r, dict)]
    if not records:
        raise ParseError("no objects found in JSON")
    return records


# --------------------------------------------------------------------------- #
# JSON-LD (knowledge-graph exports, e.g. ORKG annotations)                     #
# --------------------------------------------------------------------------- #
# @type values that indicate a citable work (vs. author/venue/etc. graph nodes).
_PAPER_TYPES = (
    "article", "paper", "publication", "creativework", "scholarlyarticle",
    "book", "document", "dataset", "contribution", "comparison", "thesis", "report",
)


def _is_jsonld(payload: Any) -> bool:
    if isinstance(payload, dict):
        return "@graph" in payload or "@context" in payload or "@id" in payload
    if isinstance(payload, list):
        return any(isinstance(n, dict) and ("@id" in n or "@type" in n) for n in payload)
    return False


def _jsonld_local_key(key: str) -> str:
    """Reduce a JSON-LD key to its local term: @type->type, IRIs/prefixes->last segment."""
    if key.startswith("@"):
        return key[1:]
    for sep in ("#", "/", ":"):
        if sep in key:
            key = key.rsplit(sep, 1)[-1]
    return key


def _jsonld_value(value: Any) -> Any:
    """Unwrap JSON-LD value objects ({"@value": x} / {"@id": x} / name) and lists."""
    if isinstance(value, dict):
        return value.get("@value") or value.get("@id") or value.get("name") or None
    if isinstance(value, list):
        out = [_jsonld_value(v) for v in value]
        out = [v for v in out if v not in (None, "")]
        return out if len(out) != 1 else out[0]
    return value


def _normalize_jsonld_node(node: dict[str, Any]) -> dict[str, Any]:
    return {_jsonld_local_key(k): _jsonld_value(v) for k, v in node.items()}


def _node_types(norm: dict[str, Any]) -> list[str]:
    raw = norm.get("type")
    values = raw if isinstance(raw, list) else [raw]
    return [str(v).lower() for v in values if v]


def _parse_jsonld(payload: Any) -> list[SourceRecord]:
    if isinstance(payload, dict) and isinstance(payload.get("@graph"), list):
        nodes = payload["@graph"]
    elif isinstance(payload, list):
        nodes = payload
    else:
        nodes = [payload]

    records: list[SourceRecord] = []
    types_seen: set[str] = set()
    for node in nodes:
        if not isinstance(node, dict):
            continue
        norm = _normalize_jsonld_node(node)
        types = _node_types(norm)
        types_seen.update(types)
        record = _record_from_mapping(norm)
        if _is_paperlike(types, record):
            records.append(record)

    if not records:
        raise ParseError(
            "no citable works found in JSON-LD "
            f"(node types seen: {sorted(types_seen) or 'none'})"
        )
    return records


def _is_paperlike(types: list[str], record: SourceRecord) -> bool:
    if any(any(pt in t for pt in _PAPER_TYPES) for t in types):
        return bool(record.title or record.doi or record.full_text)
    if types:  # typed, but not a work (Person/Organization/Venue/...) -> skip
        return False
    # Untyped node: keep only if it clearly looks like a work.
    return bool(record.title and (record.abstract or record.doi or record.authors or record.year))


def _parse_pdf(data: bytes) -> list[SourceRecord]:
    import fitz  # pymupdf; imported lazily to keep import cost off the hot path

    try:
        doc = fitz.open(stream=data, filetype="pdf")
    except Exception as exc:  # pragma: no cover - pymupdf raises broad errors
        raise ParseError(f"could not open PDF: {exc}") from exc

    pages = [page.get_text("text") for page in doc]
    meta_title = (doc.metadata or {}).get("title", "") if doc.metadata else ""
    doc.close()
    full_text = "\n".join(pages).strip()
    if not full_text:
        raise ParseError("no extractable text in PDF (scanned/image PDFs need OCR)")

    return [
        SourceRecord(
            title=(meta_title or _guess_title(full_text)).strip(),
            abstract=_guess_abstract(full_text),
            full_text=full_text,
            raw={"pages": len(pages)},
        )
    ]


def _guess_title(text: str) -> str:
    for line in text.splitlines():
        line = line.strip()
        if len(line) > 8:
            return line[:300]
    return "Untitled document"


def _guess_abstract(text: str) -> str:
    match = re.search(r"abstract\b[:\s]*(.+?)(?:\n\s*\n|\bkeywords\b|\b1\.?\s+introduction\b)",
                      text, flags=re.IGNORECASE | re.DOTALL)
    if match:
        return " ".join(match.group(1).split())[:2000]
    return ""
