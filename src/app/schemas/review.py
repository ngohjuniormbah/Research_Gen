import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .source_record import SourceRecord


class ReviewCreate(BaseModel):
    topic: str = Field(
        min_length=1, max_length=10000,  # Expanded from 1,000 to 10,000
        description="Subject of the literature review.",
        examples=["Graph neural networks for molecular property prediction"],
    )
    instructions: str | None = Field(
        default=None, max_length=10000,  # Expanded from 2,000 to 10,000
        description="Optional natural-language guidance that steers the review.",
    )
    provider: str | None = Field(
        default=None, description="LLM registry key; omit to use the configured default.",
    )
    records: list[SourceRecord] = Field(default_factory=list)
    document_ids: list[uuid.UUID] = Field(default_factory=list)
    orkg_query: str | None = Field(
        default=None, max_length=1000,
    )
    orkg_size: int = Field(default=20, ge=1, le=100)
    max_tokens: int | None = Field(default=None, ge=64, le=32768)

    # Bring-Your-Own-Key (BYOK)
    api_key: str | None = None
    model: str | None = None
    vendor: str | None = None
    base_url: str | None = None

    @field_validator("topic")
    @classmethod
    def _topic_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("topic must not be blank")
        return value.strip()


class MultiReviewCreate(ReviewCreate):
    providers: list[str] = Field(min_length=1, max_length=5)


class MultiReviewItem(BaseModel):
    provider: str
    model: str = ""
    review_id: uuid.UUID | None = None
    content_md: str = ""
    structured: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None


class MultiReviewOut(BaseModel):
    results: list[MultiReviewItem] = Field(default_factory=list)


class Citation(BaseModel):
    marker: str
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
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    topic: str
    provider: str
    model: str
    created_at: datetime
    sections: int = 0


class ReviewUpdate(BaseModel):
    topic: str = Field(min_length=1, max_length=5000)

    @field_validator("topic")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("topic must not be blank")
        return value.strip()


class ReviewEvaluateRequest(BaseModel):
    provider: str | None = None
    api_key: str | None = None
    model: str | None = None
    vendor: str | None = None
    rubric: str | None = None


class EvaluationMetric(BaseModel):
    score: int = Field(ge=1, le=10)
    feedback: str


class ReviewEvaluationOut(BaseModel):
    review_id: uuid.UUID
    judge_provider: str
    judge_model: str
    overall_score: float
    grounding: EvaluationMetric
    citation_accuracy: EvaluationMetric
    completeness: EvaluationMetric
    academic_rigor: EvaluationMetric
    critique_summary: str
    created_at: datetime
