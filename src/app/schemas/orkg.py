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


class OrkgAsk(BaseModel):
    """Natural-language ORKG retrieval request."""

    query: str = Field(
        min_length=1, max_length=1000,
        description="Plain-language research request; SPARQL is generated server-side.",
        examples=["machine learning approaches for malaria detection between 2020 and 2025"],
    )
    size: int = Field(default=20, ge=1, le=100)
    provider: str | None = Field(
        default=None, description="LLM registry key used to plan the query; omit for default.",
    )


class OrkgAskResult(BaseModel):
    request: str
    mode: str  # "sparql" | "search"
    count: int
    records: list[dict[str, Any]] = Field(default_factory=list)
    sparql: str | None = None
    sparql_error: str | None = None
    columns: list[str] = Field(default_factory=list)


class OrkgResolve(BaseModel):
    """Resolve pasted references (ORKG URLs/ids, DOIs, titles) into structured sources."""

    inputs: str = Field(
        min_length=1, max_length=10000,
        description="ORKG URLs, ORKG ids, DOIs, and/or paper titles — one per line, or "
        "comma-separated when each item is an id/DOI/URL.",
    )


class OrkgResolveResult(BaseModel):
    count: int
    resolved: int
    records: list[dict[str, Any]] = Field(default_factory=list)
    unresolved: list[str] = Field(default_factory=list)


class SparqlQuery(BaseModel):
    query: str = Field(min_length=1)
    # Optional client-requested cap; guardrails still enforce the hard max.
    limit: int | None = None


class SparqlResult(BaseModel):
    columns: list[str] = Field(default_factory=list)
    rows: list[dict[str, Any]] = Field(default_factory=list)
    raw: dict[str, Any] = Field(default_factory=dict)
