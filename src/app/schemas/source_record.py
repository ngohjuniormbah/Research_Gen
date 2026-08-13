from typing import Any

from pydantic import BaseModel, Field


class SourceRecord(BaseModel):
    """The single canonical record every parser emits and every downstream stage
    consumes. CSV, XLSX, PDF and JSON ingestion all normalize to this shape."""

    title: str = ""
    abstract: str = ""
    authors: list[str] = Field(default_factory=list)
    year: int | None = None
    venue: str = ""
    doi: str = ""
    full_text: str | None = None
    # The original, pre-normalization payload for this record (provenance/debugging).
    raw: dict[str, Any] = Field(default_factory=dict)

    def dedupe_key(self) -> str:
        """Stable identity used for de-duplication: DOI wins, else title+year."""
        if self.doi:
            return f"doi:{self.doi.strip().lower()}"
        title = " ".join(self.title.lower().split())
        return f"ty:{title}|{self.year or ''}"
