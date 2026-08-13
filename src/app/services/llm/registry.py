"""Config-driven provider registry. Adding a selectable model = one entry in
``settings.llm_providers`` (or the LLM_PROVIDERS env var). No code changes."""

from __future__ import annotations

from functools import lru_cache

from ...config import Settings, get_settings
from .base import LLMProvider
from .fake import FakeProvider
from .openai_client import OpenAICompatProvider


class ProviderRegistry:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._cache: dict[str, LLMProvider] = {}

    @property
    def settings(self) -> Settings:
        return self._settings

    @property
    def keys(self) -> list[str]:
        return list(self._settings.llm_providers.keys())

    def default_key(self) -> str:
        return self._settings.llm_default_provider

    def get(self, key: str | None = None) -> LLMProvider:
        key = key or self.default_key()
        if key in self._cache:
            return self._cache[key]
        config = self._settings.llm_providers.get(key)
        if config is None:
            raise KeyError(
                f"unknown provider '{key}'. Available: {sorted(self._settings.llm_providers)}"
            )
        provider: LLMProvider
        if config.kind == "fake":
            provider = FakeProvider(key=key, model=config.model or "fake-1")
        else:
            provider = OpenAICompatProvider(
                key=key,
                base_url=config.base_url,
                model=config.model,
                api_key=config.api_key,
                timeout_s=self._settings.llm_request_timeout_s,
            )
        self._cache[key] = provider
        return provider


@lru_cache
def get_registry() -> ProviderRegistry:
    return ProviderRegistry(get_settings())


def get_provider(key: str | None = None) -> LLMProvider:
    return get_registry().get(key)
