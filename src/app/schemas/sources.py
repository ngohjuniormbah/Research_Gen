from typing import Any

from pydantic import BaseModel, Field


class SourcesSearchResult(BaseModel):
    query: str
    count: int
    providers: list[str] = Field(default_factory=list)
    records: list[dict[str, Any]] = Field(default_factory=list)
