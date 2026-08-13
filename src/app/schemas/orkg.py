from typing import Any

from pydantic import BaseModel, Field


class OrkgConnect(BaseModel):
    """Obtain and store an ORKG OIDC token via the Resource Owner Password grant."""

    username: str
    password: str


class OrkgConnectResult(BaseModel):
    connected: bool
    expires_in: int = 0


class OrkgSearchResult(BaseModel):
    query: str
    total: int
    items: list[dict[str, Any]] = Field(default_factory=list)


class SparqlQuery(BaseModel):
    query: str = Field(min_length=1)
    # Optional client-requested cap; guardrails still enforce the hard max.
    limit: int | None = None


class SparqlResult(BaseModel):
    columns: list[str] = Field(default_factory=list)
    rows: list[dict[str, Any]] = Field(default_factory=list)
    raw: dict[str, Any] = Field(default_factory=dict)
