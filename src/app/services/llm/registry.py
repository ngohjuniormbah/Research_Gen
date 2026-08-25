"""Config-driven provider registry. Adding a selectable model = one entry in
``settings.llm_providers`` (or the LLM_PROVIDERS env var). No code changes."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from ...config import Settings, get_settings
from .base import LLMProvider
from .fake import FakeProvider
from .openai_client import OpenAICompatProvider

# Bring-Your-Own-Key vendors. Each speaks the OpenAI `/chat/completions` schema (Anthropic
# via its OpenAI-compatibility endpoint), so one client covers them all. (base_url, default_model)
BYOK_VENDORS: dict[str, tuple[str, str]] = {
    "openai": ("https://api.openai.com/v1", "gpt-4o-mini"),
    "openrouter": ("https://openrouter.ai/api/v1", "meta-llama/llama-3.3-70b-instruct"),
    "groq": ("https://api.groq.com/openai/v1", "llama-3.3-70b-versatile"),
    "anthropic": ("https://api.anthropic.com/v1", "claude-3-5-haiku-latest"),
}


@dataclass
class Byok:
    """A client-provided API key and optional routing, from request headers. Never stored."""

    api_key: str
    vendor: str = ""  # "" -> override the selected registered provider's key; else route to vendor
    model: str = ""
    base_url: str = ""

    @property
    def active(self) -> bool:
        return bool(self.api_key)


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

    def get(self, key: str | None = None, *, api_key: str | None = None) -> LLMProvider:
        key = key or self.default_key()
        # A caller-supplied key overrides the configured one; such providers are never
        # cached (the key is per-request and must not leak to other callers).
        if api_key is None and key in self._cache:
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
                api_key=api_key or config.api_key,
                timeout_s=self._settings.llm_request_timeout_s,
            )
        if api_key is None:
            self._cache[key] = provider
        return provider

    def resolve(self, key: str | None, byok: Byok | None) -> LLMProvider:
        """Pick the provider for a request, honoring a client-provided key (BYOK).

        * BYOK with an explicit vendor -> build a fresh vendor provider (openai/openrouter/
          groq/anthropic), model from the header or the vendor default.
        * BYOK without a vendor -> use the selected registered provider but with the
          caller's key (e.g. their OpenRouter key overriding the system key).
        * No BYOK -> the registered provider as usual."""
        if byok and byok.active and byok.vendor:
            base_default, model_default = BYOK_VENDORS.get(
                byok.vendor.lower(), BYOK_VENDORS["openai"]
            )
            return OpenAICompatProvider(
                key=f"byok:{byok.vendor.lower()}",
                base_url=byok.base_url or base_default,
                model=byok.model or model_default,
                api_key=byok.api_key,
                timeout_s=self._settings.llm_request_timeout_s,
            )
        if byok and byok.active:
            return self.get(key, api_key=byok.api_key)
        return self.get(key)


@lru_cache
def get_registry() -> ProviderRegistry:
    return ProviderRegistry(get_settings())


def get_provider(key: str | None = None) -> LLMProvider:
    return get_registry().get(key)
