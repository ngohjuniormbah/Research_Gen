"""Normalization & cleaning: fix whitespace/encoding, unify authors, and de-duplicate
into a single list[SourceRecord]."""

from __future__ import annotations

import re
import unicodedata

from ...schemas.source_record import SourceRecord

_WS = re.compile(r"\s+")


def _clean_text(value: str) -> str:
    if not value:
        return ""
    # Normalize unicode (NFKC folds ligatures/full-width forms) and collapse whitespace.
    value = unicodedata.normalize("NFKC", value)
    value = value.replace("\x00", "")
    return _WS.sub(" ", value).strip()


def _clean_doi(doi: str) -> str:
    doi = _clean_text(doi).lower()
    doi = re.sub(r"^(https?://)?(dx\.)?doi\.org/", "", doi)
    return doi.removeprefix("doi:").strip()


def clean_record(record: SourceRecord) -> SourceRecord:
    authors = []
    seen_authors: set[str] = set()
    for author in record.authors:
        cleaned = _clean_text(author)
        key = cleaned.lower()
        if cleaned and key not in seen_authors:
            seen_authors.add(key)
            authors.append(cleaned)
    return record.model_copy(
        update={
            "title": _clean_text(record.title),
            "abstract": _clean_text(record.abstract),
            "venue": _clean_text(record.venue),
            "doi": _clean_doi(record.doi),
            "authors": authors,
            "full_text": _clean_text(record.full_text) if record.full_text else record.full_text,
        }
    )


def _merge(base: SourceRecord, other: SourceRecord) -> SourceRecord:
    """Fill blanks in ``base`` from a duplicate ``other`` (keep the richer record)."""
    update = {}
    for field in ("title", "abstract", "venue", "doi"):
        if not getattr(base, field) and getattr(other, field):
            update[field] = getattr(other, field)
    if base.year is None and other.year is not None:
        update["year"] = other.year
    if not base.authors and other.authors:
        update["authors"] = other.authors
    if not base.full_text and other.full_text:
        update["full_text"] = other.full_text
    return base.model_copy(update=update) if update else base


def normalize_records(records: list[SourceRecord]) -> list[SourceRecord]:
    """Clean, then de-duplicate by DOI (or title+year), merging complementary fields.

    Empty records (no title, doi or full_text) are dropped.
    """
    out: list[SourceRecord] = []
    index: dict[str, int] = {}
    for record in records:
        cleaned = clean_record(record)
        if not (cleaned.title or cleaned.doi or cleaned.full_text):
            continue
        key = cleaned.dedupe_key()
        if key in index:
            pos = index[key]
            out[pos] = _merge(out[pos], cleaned)
        else:
            index[key] = len(out)
            out.append(cleaned)
    return out
