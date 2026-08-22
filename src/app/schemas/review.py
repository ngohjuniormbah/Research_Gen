import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .source_record import SourceRecord


class ReviewCreate(BaseModel):
    topic: str = Field(
        min_length=1, max_length=1000,
        description="Subject of the literature review.",
        examples=["Graph neural networks for molecular property prediction"],
    )
    instructions: str | None = Field(
        default=None, max_length=2000,
        description="Optional natural-language guidance that steers the review "
        "(tone, length, focus, sections).",
        examples=["Focus on methods since 2020 and keep it under 500 words."],
    )
    provider: str | None = Field(
        default=None, description="LLM registry key; omit to use the configured default.",
        examples=["fake"],
    )
    # Sources: inline records, previously uploaded documents, and/or an ORKG query the
    # backend runs and folds into the review (at least one source is required).
    records: list[SourceRecord] = Field(default_factory=list)
    document_ids: list[uuid.UUID] = Field(default_factory=list)
    orkg_query: str | None = Field(
        default=None, max_length=500,
        description="If set, the backend searches ORKG for this query and uses the "
        "results as sources for the review.",
        examples=["knowledge graphs"],
    )
    orkg_size: int = Field(default=20, ge=1, le=100)
    max_tokens: int | None = Field(default=None, ge=64, le=8192)

    @field_validator("topic")
    @classmethod
    def _topic_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("topic must not be blank")
        return value.strip()


class Citation(BaseModel):
    marker: str  # e.g. "[1]"
    source_index: int
    title: str = ""


class ReviewSection(BaseModel):
    heading: str
    content: str


class ReviewOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    job_id: uuid.UUID | None
    topic: str
    provider: str
    model: str
    content_md: str
    structured: dict[str, Any]
    csl_json: list[dict[str, Any]] = Field(default_factory=list)
    created_at: datetime


class PreviewOut(BaseModel):
    id: uuid.UUID
    format: str
    html: str


class ReviewSummary(BaseModel):
    """Compact row for the 'past work' list (no heavy content_md/structured payload)."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    topic: str
    provider: str
    model: str
    created_at: datetime
    sections: int = 0


class ReviewUpdate(BaseModel):
    topic: str = Field(min_length=1, max_length=1000, description="New title for the review.")

    @field_validator("topic")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("topic must not be blank")
        return value.strip()
