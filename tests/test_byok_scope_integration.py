"""Integration test for Research-only scope guardrails and BYOK credentials."""

import json
from httpx import AsyncClient

from app.api.v1.reviews import _byok_from_request
from app.schemas.review import ReviewCreate


async def test_scope_guard_blocks_casual_queries(client: AsyncClient, auth_headers: dict) -> None:
    """Non-academic and casual chat prompts must be rejected with HTTP 422."""
    resp = await client.post(
        "/api/v1/reviews",
        headers=auth_headers,
        json={"topic": "tell me a joke about cats",
              "records": [{"title": "Paper A"}]},
    )
    assert resp.status_code == 422
    body = resp.json()
    assert body["error"]["code"] == "validation_error"
    assert "Research Scope" in body["error"]["message"]


async def test_scope_guard_allows_research_queries(client: AsyncClient, auth_headers: dict) -> None:
    """Scientific research topics must pass through cleanly."""
    resp = await client.post(
        "/api/v1/reviews",
        headers=auth_headers,
        json={
            "topic": "Graph neural networks for molecular property prediction",
            "records": [{"title": "GNN in Chemistry", "year": 2021}],
        },
    )
    assert resp.status_code == 202
    assert resp.json()["status"] == "succeeded"


async def test_stream_refusal_on_off_topic(client: AsyncClient, auth_headers: dict) -> None:
    """Live streaming endpoint should stream the refusal notice instead of crashing."""
    tokens = []
    async with client.stream(
        "POST",
        "/api/v1/reviews/stream",
        headers=auth_headers,
        json={"topic": "recipe for chocolate cake"},
    ) as resp:
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]
        async for line in resp.aiter_lines():
            if line.startswith("data:"):
                payload = json.loads(line[len("data:"):].strip())
                if payload.get("type") == "token":
                    tokens.append(payload["text"])

    assert any("Research Scope" in t for t in tokens)


def test_byok_from_request_uses_body_parameters() -> None:
    """Credentials supplied inside the JSON body must be parsed properly."""
    body = ReviewCreate(
        topic="transformers in genomics",
        api_key="sk-body-custom-key",
        vendor="groq",
        model="llama-3.3-70b",
    )
    byok = _byok_from_request(body)
    assert byok is not None
    assert byok.api_key == "sk-body-custom-key"
    assert byok.vendor == "groq"
    assert byok.model == "llama-3.3-70b"


def test_byok_from_request_prefers_headers_over_body() -> None:
    """Header overrides should take precedence if both headers and body are provided."""
    body = ReviewCreate(
        topic="neural architecture search",
        api_key="sk-body-key",
        vendor="openai",
        model="gpt-4o-mini",
    )
    byok = _byok_from_request(
        body,
        header_key="sk-header-key",
        header_vendor="openrouter",
        header_model="anthropic/claude-3.5-sonnet",
    )
    assert byok is not None
    assert byok.api_key == "sk-header-key"
    assert byok.vendor == "openrouter"
    assert byok.model == "anthropic/claude-3.5-sonnet"
