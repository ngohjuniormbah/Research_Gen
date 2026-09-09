"""Config-driven provider registry. Adding a selectable model = one entry in
settings.llm_providers (or the LLM_PROVIDERS env var)."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from ...config import Settings, get_settings
from .base import LLMProvider
from .fake import FakeProvider
from .openai_client import OpenAICompatProvider

# Supported Bring-Your-Own-Key providers: (base_url, default_model)
BYOK_VENDORS: dict[str, tuple[str, str]] = {
    "openai": ("https://api.openai.com/v1", "gpt-4o-mini"),
    "openrouter": ("https://openrouter.ai/api/v1", "meta-llama/llama-3.3-70b-instruct"),
    "groq": ("https://api.groq.com/openai/v1", "llama-3.3-70b-versatile"),
    "anthropic": ("https://api.anthropic.com/v1", "claude-3-5-sonnet-20241022"),
    "deepseek": ("https://api.deepseek.com/v1", "deepseek-chat"),
}


@dataclass
class Byok:
    """Client-provided API key and optional model routing. Never stored server-side."""

    api_key: str
    vendor: str = ""
    model: str = ""
    base_url: str = ""

    @property
    def active(self) -> bool:
        return bool(self.api_key and self.api_key.strip())


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

    def get(self, key: str | None = None, *, api_key: str | None = None, model: str | None = None) -> LLMProvider:
        key = key or self.default_key()

        # Ephemeral custom providers are not cached to prevent cross-user key leaks
        if api_key is not None and api_key.strip():
            config = self._settings.llm_providers.get(key)
            base_url = config.base_url if config else "https://api.openai.com/v1"
            target_model = model or (config.model if config else "gpt-4o-mini")
            return OpenAICompatProvider(
                key=key,
                base_url=base_url,
                model=target_model,
                api_key=api_key.strip(),
                timeout_s=self._settings.llm_request_timeout_s,
            )

        if key in self._cache:
            return self._cache[key]

        config = self._settings.llm_providers.get(key)
        if config is None:
            raise KeyError(
                f"unknown provider '{key}'. Available: {sorted(self._settings.llm_providers)}"
            )

        if config.kind == "fake":
            provider: LLMProvider = FakeProvider(
                key=key, model=config.model or "fake-1")
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

    def resolve(self, key: str | None, byok: Byok | None) -> LLMProvider:
        """Resolve the model provider, prioritizing any client-supplied key."""
        if byok and byok.active:
            vendor_name = byok.vendor.lower().strip()
            if vendor_name and vendor_name in BYOK_VENDORS:
                default_url, default_model = BYOK_VENDORS[vendor_name]
                return OpenAICompatProvider(
                    key=f"byok:{vendor_name}",
                    base_url=byok.base_url or default_url,
                    model=byok.model or default_model,
                    api_key=byok.api_key,
                    timeout_s=self._settings.llm_request_timeout_s,
                )
            # Route to configured provider with the user's override key
            return self.get(key, api_key=byok.api_key, model=byok.model or None)

        return self.get(key)


@lru_cache
def get_registry() -> ProviderRegistry:
    return ProviderRegistry(get_settings())


def get_provider(key: str | None = None) -> LLMProvider:
    return get_registry().get(key)
