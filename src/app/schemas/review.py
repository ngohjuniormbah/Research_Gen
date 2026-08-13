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
    provider: str | None = Field(
        default=None, description="LLM registry key; omit to use the configured default.",
        examples=["fake"],
    )
    # Provide records inline and/or reference previously uploaded documents.
    records: list[SourceRecord] = Field(default_factory=list)
    document_ids: list[uuid.UUID] = Field(default_factory=list)
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
