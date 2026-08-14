import pytest

from app.config import get_settings
from app.schemas.source_record import SourceRecord
from app.services.context import build_context, estimate_tokens
from app.services.llm.registry import ProviderRegistry, get_provider
from app.services.review import generate_review_content


def _records(n: int, abstract_len: int = 20) -> list[SourceRecord]:
    return [
        SourceRecord(title=f"Paper {i}", abstract="word " * abstract_len, year=2000 + i)
        for i in range(n)
    ]


def test_build_context_direct() -> None:
    bundle = build_context(_records(3), token_budget=10_000)
    assert bundle.strategy == "direct"
    assert bundle.included == 3
    assert bundle.dropped == 0
    assert "[1]" in bundle.sources_block and "[3]" in bundle.sources_block


def test_build_context_mapreduce_when_over_budget() -> None:
    bundle = build_context(_records(50, abstract_len=100), token_budget=300)
    assert bundle.strategy == "map-reduce"
    assert bundle.token_estimate <= 300
    # Either abstracts were truncated to fit, or some sources were dropped.
    assert bundle.included >= 1


def test_estimate_tokens_monotonic() -> None:
    assert estimate_tokens("a" * 40) == 10
    assert estimate_tokens("") == 0


def test_fake_provider_is_default() -> None:
    provider = get_provider()
    assert provider.key == "fake"


def test_registry_unknown_provider_raises() -> None:
    reg = ProviderRegistry(get_settings())
    with pytest.raises(KeyError):
        reg.get("does-not-exist")


def test_registry_lists_expected_models() -> None:
    reg = ProviderRegistry(get_settings())
    for key in ("fake", "gemma", "qwen", "deepseek-v4", "glm"):
        assert key in reg.keys


def test_render_prompt_includes_instructions() -> None:
    from app.services.prompts import render_review_prompt

    prompt = render_review_prompt("topic", "[1] Source", "focus on methods since 2020")
    assert "focus on methods since 2020" in prompt
    # No instructions -> no leftover template placeholder.
    assert "{instructions}" not in render_review_prompt("t", "[1] X")


async def test_instructions_recorded_in_structured() -> None:
    result = await generate_review_content(
        provider=get_provider("fake"),
        topic="t",
        records=_records(2),
        instructions="Keep it under 300 words.",
    )
    assert result.structured["instructions"] == "Keep it under 300 words."


async def test_generate_review_content_structured() -> None:
    provider = get_provider("fake")
    result = await generate_review_content(
        provider=provider,
        topic="graph neural networks",
        records=_records(3),
        token_budget=10_000,
    )
    assert "# Literature Review" in result.content_md
    sections = {s["heading"] for s in result.structured["sections"]}
    assert "Introduction" in sections
    assert "References" in sections
    # Citations were extracted and map back to sources.
    markers = {c["marker"] for c in result.structured["citations"]}
    assert "[1]" in markers
    assert len(result.structured["sources"]) == 3
