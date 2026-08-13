import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from .source_record import SourceRecord


class ReviewCreate(BaseModel):
    topic: str = Field(min_length=1, max_length=1000)
    provider: str | None = None  # registry key; None -> configured default
    # Provide records inline and/or reference previously uploaded documents.
    records: list[SourceRecord] = Field(default_factory=list)
    document_ids: list[uuid.UUID] = Field(default_factory=list)
    max_tokens: int | None = None


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
    structured: dict
    created_at: datetime
