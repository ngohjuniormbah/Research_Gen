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
_ALIASES: dict[str, tuple[str, ...]] = {
    "title": ("title", "name", "paper_title", "article_title"),
    "abstract": ("abstract", "summary", "description"),
    "authors": ("authors", "author", "author_names", "creators"),
    "year": ("year", "publication_year", "pub_year", "date", "published"),
    "venue": ("venue", "journal", "conference", "publisher", "source", "booktitle"),
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


def parse_bytes(data: bytes, filename: str, content_type: str = "") -> list[SourceRecord]:
    kind = detect_kind(filename, content_type)
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
