"""BYOK provider routing and exhaustive table rendering into the prompt context."""
from __future__ import annotations

from app.config import ProviderConfig, Settings
from app.schemas.source_record import SourceRecord
from app.services.context import build_context
from app.services.llm.registry import Byok, ProviderRegistry


def _settings() -> Settings:
    return Settings(
        llm_providers={
            "fake": ProviderConfig(kind="fake", model="fake-1"),
            "cloud": ProviderConfig(base_url="https://sys.example/v1", model="sys-model",
                                    api_key="SYSTEM-KEY", kind="openai"),
        },
        llm_default_provider="fake",
    )


def test_byok_vendor_builds_vendor_provider() -> None:
    reg = ProviderRegistry(_settings())
    p = reg.resolve(None, Byok(api_key="sk-user", vendor="groq"))
    assert p.key == "byok:groq"
    assert p.model == "llama-3.3-70b-versatile"  # groq default model
    assert p._api_key == "sk-user"  # type: ignore[attr-defined]


def test_byok_model_override() -> None:
    reg = ProviderRegistry(_settings())
    p = reg.resolve(None, Byok(api_key="sk", vendor="openrouter", model="x-ai/grok"))
    assert p.model == "x-ai/grok"


def test_byok_without_vendor_overrides_registered_key() -> None:
    reg = ProviderRegistry(_settings())
    p = reg.resolve("cloud", Byok(api_key="sk-user"))
    assert p.model == "sys-model"  # same model route
    assert p._api_key == "sk-user"  # type: ignore[attr-defined]  # caller's key wins


def test_no_byok_uses_registered_provider() -> None:
    reg = ProviderRegistry(_settings())
    p = reg.resolve("cloud", None)
    assert p._api_key == "SYSTEM-KEY"  # type: ignore[attr-defined]


def test_byok_provider_not_cached() -> None:
    reg = ProviderRegistry(_settings())
    a = reg.get("cloud", api_key="one")
    b = reg.get("cloud")  # no override -> the cached, system-key provider
    assert a._api_key == "one"  # type: ignore[attr-defined]
    assert b._api_key == "SYSTEM-KEY"  # type: ignore[attr-defined]


def test_all_tables_rendered_into_context() -> None:
    # A single PDF-like source carrying THREE comparison tables — every one must appear.
    rec = SourceRecord(
        title="Survey with many comparisons",
        full_text="Intro prose.",
        raw={"tables": [
            {"page": 2, "rows": [["Paper", "Accuracy"], ["ResNet", "0.97"]]},
            {"page": 3, "rows": [["Paper", "Dataset"], ["VGG", "ImageNet"]]},
            {"page": 4, "rows": [["Paper", "Metric"], ["ViT", "F1=0.9"]]},
        ]},
    )
    bundle = build_context([rec], token_budget=8000)
    block = bundle.sources_block
    for marker in ("Table 1 (page 2)", "Table 2 (page 3)", "Table 3 (page 4)"):
        assert marker in block
    assert "ResNet" in block and "VGG" in block and "ViT" in block  # no table dropped


def test_tables_survive_compression() -> None:
    # Even when prose overflows the budget, the structured tables are kept.
    big = "word " * 20000
    rec = SourceRecord(
        title="Huge doc", full_text=big,
        raw={"tables": [{"page": 1, "rows": [["Paper", "Result"], ["Study-Z", "SOTA"]]}]},
    )
    bundle = build_context([rec], token_budget=300)
    assert "Study-Z" in bundle.sources_block  # table retained despite tight budget
