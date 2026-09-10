"""File ingestion with enhanced support for multi-table extraction, high-resolution OCR,
and normalized Markdown tables."""

from __future__ import annotations

import io
import json
import re
import time
from typing import Any

import pandas as pd

from ...schemas.source_record import SourceRecord

SUPPORTED = ("csv", "xlsx", "pdf", "json")


class ParseError(Exception):
    """Raised when an upload cannot be parsed into SourceRecords."""


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
    raise ParseError(
        f"unsupported file type: filename={filename!r} content_type={ct!r}")


def sniff_kind(data: bytes, filename: str = "", content_type: str = "") -> str:
    """Determine the file kind from content and bytes."""
    if not data:
        raise ParseError("empty file")

    name = (filename or "").lower()
    ct = (content_type or "").lower()

    header_sample = data[:1024]
    if b"%PDF-" in header_sample or b"%PDF" in header_sample or name.endswith(".pdf") or "pdf" in ct:
        if b"%PDF" in header_sample or name.endswith(".pdf"):
            return "pdf"

    if data[:4] == b"PK\x03\x04":
        if name.endswith((".xlsx", ".xlsm", ".xls")) or "sheet" in ct or "excel" in ct:
            return "xlsx"
        raise ParseError(
            "zip-based upload is not a supported spreadsheet (.xlsx)")

    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        try:
            text = data.decode("latin-1")
        except Exception as exc:
            raise ParseError(
                "file is not valid text or a supported binary format") from exc

    stripped = text.lstrip()
    if stripped[:1] in ("{", "[") or name.endswith(".json") or "json" in ct:
        return "json"
    if name.endswith(".csv") or "csv" in ct or ("," in text or "\n" in text or ";" in text or "\t" in text):
        return "csv"

    raise ParseError(
        "could not identify a supported file type from its contents")


def parse_bytes(data: bytes, filename: str, content_type: str = "") -> list[SourceRecord]:
    kind = sniff_kind(data, filename, content_type)
    if kind == "csv":
        return _parse_tabular(_read_csv_robust(data))
    if kind == "xlsx":
        return _parse_tabular(pd.read_excel(io.BytesIO(data)))
    if kind == "json":
        return _parse_json(data)
    if kind == "pdf":
        return _parse_pdf(data, filename)
    raise ParseError(f"unsupported file type: {kind}")


# --------------------------------------------------------------------------- #
# Helpers                                                                     #
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
        full_text=(str(_pick(row, "full_text")).strip()
                   if _pick(row, "full_text") else None),
        raw={k: _jsonable(v) for k, v in row.items()},
    )


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool, list, dict)):
        return value
    if not _present(value):
        return None
    return str(value)


def _read_csv_robust(data: bytes) -> pd.DataFrame:
    last_exc: Exception | None = None
    for encoding in ("utf-8", "utf-8-sig", "latin-1", "cp1252"):
        try:
            return pd.read_csv(io.BytesIO(data), sep=None, engine="python", encoding=encoding)
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
    try:
        return pd.read_csv(io.BytesIO(data))
    except Exception as exc:  # noqa: BLE001
        raise ParseError(f"could not parse CSV: {last_exc or exc}") from (
            last_exc or exc)


def _parse_tabular(df: pd.DataFrame) -> list[SourceRecord]:
    records = [_record_from_mapping(row)
               for row in df.to_dict(orient="records")]
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
        raise ParseError(
            "JSON must be a list of objects or an object wrapping one")
    records = [_record_from_mapping(r) for r in rows if isinstance(r, dict)]
    if not records:
        raise ParseError("no objects found in JSON")
    return records


# --------------------------------------------------------------------------- #
# JSON-LD handling                                                            #
# --------------------------------------------------------------------------- #
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
    if key.startswith("@"):
        return key[1:]
    for sep in ("#", "/", ":"):
        if sep in key:
            key = key.rsplit(sep, 1)[-1]
    return key


def _jsonld_value(value: Any) -> Any:
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
    if types:
        return False
    return bool(record.title and (record.abstract or record.doi or record.authors or record.year))


# --------------------------------------------------------------------------- #
# Enhanced PDF & OCR Engine (Scaled for 48+ Tables)                           #
# --------------------------------------------------------------------------- #
_OCR_MAX_PAGES = 40
_OCR_DPI = 200
_OCR_TIME_BUDGET_S = 90.0

# Scaled table parsing limits
_MAX_TABLES = 120             # Increased from 50 to parse all comparison tables
_MAX_TABLE_ROWS = 250         # Increased from 100 to capture full empirical tables
_MAX_DOI_RECORDS = 150        # Increased from 60 to index all references
_PDF_DOI_RE = re.compile(r"10\.\d{4,9}/[-._;()/:A-Za-z0-9]+", re.IGNORECASE)


def _extract_dois(text: str) -> list[str]:
    out: list[str] = []
    lowered: set[str] = set()
    for m in _PDF_DOI_RE.finditer(text):
        doi = m.group(0).rstrip(").,;\"'")
        if doi.lower() not in lowered:
            lowered.add(doi.lower())
            out.append(doi)
    return out


def _ocr_page_text(page: Any) -> str:
    """Adaptive OCR with image contrast enhancement."""
    try:
        import pytesseract
        from PIL import Image, ImageEnhance
    except ImportError:
        return ""
    try:
        pix = page.get_pixmap(dpi=_OCR_DPI)
        img = Image.open(io.BytesIO(pix.tobytes("png"))).convert("L")
        enhancer = ImageEnhance.Contrast(img)
        img = enhancer.enhance(1.8)
        text = str(pytesseract.image_to_string(img) or "").strip()
        img.close()
        return text
    except Exception:
        return ""


def _extract_page_text_ordered(page: Any) -> str:
    """Multi-column reading-order text extraction."""
    try:
        blocks = page.get_text("blocks")
        if not blocks:
            return ""
        text_blocks = [b for b in blocks if len(
            b) > 4 and b[4] and str(b[4]).strip()]
        text_blocks.sort(key=lambda b: (round(b[0] / 150) * 150, b[1]))
        return "\n\n".join(str(b[4]).strip() for b in text_blocks)
    except Exception:
        return page.get_text("text") or ""


def _format_table_as_markdown(rows: list[list[str]]) -> str:
    """Format structured table rows into presentable Markdown."""
    if not rows or len(rows) < 2:
        return ""
    header = [c.replace("\n", " ").strip() for c in rows[0]]
    separator = ["---"] * len(header)
    md_lines = ["| " + " | ".join(header) + " |",
                "| " + " | ".join(separator) + " |"]
    for row in rows[1:]:
        clean_row = [str(c).replace("\n", " ").strip() for c in row]
        if len(clean_row) < len(header):
            clean_row.extend([""] * (len(header) - len(clean_row)))
        md_lines.append("| " + " | ".join(clean_row[:len(header)]) + " |")
    return "\n".join(md_lines)


def _parse_pdf(data: bytes, filename: str = "") -> list[SourceRecord]:
    try:
        import pymupdf as fitz
    except ImportError:
        import fitz

    try:
        doc = fitz.open(stream=data, filetype="pdf")
    except Exception as exc:
        raise ParseError(f"could not open PDF: {exc}") from exc

    try:
        if getattr(doc, "is_encrypted", False):
            try:
                doc.authenticate("")
            except Exception:
                pass

        pages_text: list[str] = []
        tables: list[dict[str, Any]] = []
        ocr_budget = _OCR_MAX_PAGES
        ocr_deadline = time.monotonic() + _OCR_TIME_BUDGET_S

        for page_idx in range(doc.page_count):
            page = doc.load_page(page_idx)

            # 1. Native table extraction
            if len(tables) < _MAX_TABLES:
                try:
                    finder = page.find_tables()
                    for tbl in getattr(finder, "tables", []) or []:
                        if len(tables) >= _MAX_TABLES:
                            break
                        extracted_rows = tbl.extract() or []
                        if extracted_rows:
                            clean_rows = [
                                [("" if cell is None else str(cell))
                                 for cell in r]
                                for r in extracted_rows[:_MAX_TABLE_ROWS]
                            ]
                            tables.append({
                                "page": page_idx + 1,
                                "rows": clean_rows,
                                "markdown": _format_table_as_markdown(clean_rows),
                            })
                except Exception:
                    pass

            # 2. Reading-order text extraction
            text = _extract_page_text_ordered(page).strip()

            # 3. Adaptive OCR if page is image-only
            if len(text) < 40 and ocr_budget > 0 and time.monotonic() < ocr_deadline:
                ocr_result = _ocr_page_text(page)
                if ocr_result and len(ocr_result) > len(text):
                    text = ocr_result
                ocr_budget -= 1

            if text:
                pages_text.append(text)

        meta_title = (doc.metadata or {}).get(
            "title", "") if doc.metadata else ""
    finally:
        doc.close()

    full_text = "\n\n".join(pages_text).strip()
    name = (filename or "").rsplit("/", 1)[-1] or "Uploaded document"

    if not full_text:
        return [
            SourceRecord(
                title=(meta_title or name).strip(),
                abstract="",
                full_text="[No readable text could be extracted from this PDF.]",
                raw={"pages": len(pages_text), "no_text": True},
            )
        ]

    if tables:
        table_sections = [
            f"\n\n### Extracted Table (Page {t['page']}):\n{t['markdown']}"
            for t in tables if t.get("markdown")
        ]
        if table_sections:
            full_text += "\n\n## Structured Comparison Tables:\n" + \
                "\n".join(table_sections)

    dois = _extract_dois(full_text)
    primary_title = (meta_title or _guess_title(full_text, name)).strip()

    records: list[SourceRecord] = [
        SourceRecord(
            title=primary_title,
            abstract=_guess_abstract(full_text),
            full_text=full_text,
            raw={
                "pages": len(pages_text),
                "table_count": len(tables),
                "tables": tables,
                "dois": dois,
                "source": "pdf",
            },
        )
    ]

    for doi in dois[:_MAX_DOI_RECORDS]:
        records.append(
            SourceRecord(
                title=f"Referenced work (DOI {doi})",
                doi=doi,
                raw={"source": "pdf-reference", "from": primary_title},
            )
        )

    return records


def _guess_title(text: str, fallback: str) -> str:
    for line in text.splitlines():
        cleaned = line.strip()
        if len(cleaned) > 10 and not cleaned.lower().startswith(("http", "doi:", "volume", "page", "issn")):
            return cleaned[:300]
    return fallback


def _guess_abstract(text: str) -> str:
    match = re.search(
        r"\babstract\b[:\s]*(.+?)(?:\n\s*\n|\bkeywords\b|\b1[\.\s]+introduction\b|\bintroduction\b)",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if match:
        return " ".join(match.group(1).split())[:2000]
    return ""
