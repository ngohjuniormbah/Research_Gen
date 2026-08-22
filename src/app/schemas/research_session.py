import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ResearchSessionCreate(BaseModel):
    title: str = Field(default="", max_length=1000)
    state: dict[str, Any] = Field(default_factory=dict)


class ResearchSessionUpdate(BaseModel):
    """Partial update — only provided fields change."""
    title: str | None = Field(default=None, max_length=1000)
    starred: bool | None = None
    archived: bool | None = None
    state: dict[str, Any] | None = None


class ResearchSessionSummary(BaseModel):
    """Compact row for the Recent Work list (no full state payload)."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    starred: bool
    archived: bool
    created_at: datetime
    updated_at: datetime
    sources: int = 0
    outputs: int = 0


class SessionChat(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    provider: str | None = None


class ResearchSessionOut(BaseModel):
    """Full session incl. the Working-Memory state, to reopen the research context."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    starred: bool
    archived: bool
    state: dict[str, Any]
    created_at: datetime
    updated_at: datetime
