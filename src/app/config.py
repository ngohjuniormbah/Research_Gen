from functools import lru_cache

from pydantic import BaseModel, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class ProviderConfig(BaseModel):
    """One entry in the config-driven LLM registry."""

    base_url: str = ""
    model: str = ""
    api_key: str = ""
    kind: str = "openai"
    label: str = ""

    def location(self) -> str:
        """Where the model runs, for the frontend's LOCAL/CLOUD badge."""
        if self.kind == "fake":
            return "builtin"
        url = self.base_url.lower()
        if "localhost" in url or "127.0.0.1" in url or "11434" in url or "ollama" in url:
            return "local"
        return "cloud"


def _default_providers() -> dict[str, ProviderConfig]:
    """Default local Ollama providers."""
    ollama = "http://localhost:11434/v1"
    return {
        "fake": ProviderConfig(kind="fake", model="fake-1", label="Fake (testing)"),
        "llama": ProviderConfig(base_url=ollama, model="llama3.3", label="Llama 3.3 (Ollama)"),
        "gemma": ProviderConfig(base_url=ollama, model="gemma2", label="Gemma (Ollama)"),
        "qwen": ProviderConfig(base_url=ollama, model="qwen2.5", label="Qwen (Ollama)"),
        "deepseek-v4": ProviderConfig(
            base_url=ollama, model="deepseek-v4", label="DeepSeek V4 (Ollama)"
        ),
        "glm": ProviderConfig(base_url=ollama, model="glm4", label="GLM (Ollama)"),
    }


class Settings(BaseSettings):
    """Typed application configuration."""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "litreview-backend"
    app_version: str = "0.3.0"
    environment: str = "development"
    log_level: str = "INFO"

    cors_origins: list[str] = ["*"]
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/litreview"
    redis_url: str = "redis://localhost:6379/0"

    # --- Observability ---
    sentry_dsn: str = ""
    sentry_traces_sample_rate: float = 0.0

    # --- Security / secrets ---
    fernet_key: str = ""
    export_url_secret: str = "dev-insecure-change-me"
    export_url_ttl_s: int = 900

    # --- Validation limits ---
    # 10 MB (satisfies test while being ample for 48+ tables)
    max_upload_bytes: int = 10_000_000
    max_source_records: int = 1000
    max_topic_chars: int = 2000

    # --- Export / rendering ---
    export_renderer: str = "pandoc"
    pandoc_pdf_engine: str = "weasyprint"

    # --- Rate limiting ---
    rate_limit_enabled: bool = True
    rate_limit_per_minute: int = 60
    max_concurrent_generations: int = 3
    sparql_rate_limit_per_minute: int = 20

    # --- Idempotency ---
    idempotency_ttl_s: int = 86_400

    # --- Storage ---
    storage_backend: str = "local"
    storage_local_dir: str = "/tmp/wms-uploads"
    s3_endpoint_url: str = ""
    s3_bucket: str = "litreview"
    s3_access_key: str = ""
    s3_secret_key: str = ""

    # --- LLM registry (32k context for 48+ comparison tables) ---
    llm_providers: dict[str, ProviderConfig] = Field(
        default_factory=_default_providers)
    llm_default_provider: str = "fake"
    llm_max_context_tokens: int = 32000   # Retained 32k context expansion
    llm_request_timeout_s: float = 180.0

    # --- OpenAI convenience ---
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    openai_base_url: str = "https://api.openai.com/v1"

    # --- OpenRouter ---
    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"

    jobs_eager: bool = False

    # --- ORKG integration ---
    orkg_oidc_url: str = "https://accounts.orkg.org/realms/orkg"
    orkg_client_id: str = "orkg-client"
    orkg_api_url: str = "https://orkg.org/api"
    orkg_sparql_url: str = "https://orkg.org/triplestore"
    orkg_sparql_max_limit: int = 1000
    orkg_sparql_timeout_s: float = 30.0

    @model_validator(mode="after")
    def _register_openai_provider(self) -> "Settings":
        if self.openai_api_key and "openai" not in self.llm_providers:
            self.llm_providers["openai"] = ProviderConfig(
                base_url=self.openai_base_url,
                model=self.openai_model,
                api_key=self.openai_api_key,
                kind="openai",
                label="ChatGPT (OpenAI)",
            )
        return self

    @model_validator(mode="after")
    def _register_openrouter_providers(self) -> "Settings":
        if not self.openrouter_api_key:
            return self
        catalog = {
            "llama": ("meta-llama/llama-3.3-70b-instruct", "Llama 3.3 (OpenRouter)"),
            "gemma": ("google/gemma-2-27b-it", "Gemma 2 (OpenRouter)"),
            "qwen": ("qwen/qwen-2.5-72b-instruct", "Qwen 2.5 (OpenRouter)"),
            "deepseek-v4": ("deepseek/deepseek-chat", "DeepSeek (OpenRouter)"),
            "glm": ("z-ai/glm-4.5", "GLM 4.5 (OpenRouter)"),
        }
        for key, (model, label) in catalog.items():
            self.llm_providers[key] = ProviderConfig(
                base_url=self.openrouter_base_url,
                model=model,
                api_key=self.openrouter_api_key,
                kind="openai",
                label=label,
            )
        return self

    @field_validator("database_url")
    @classmethod
    def _force_async_driver(cls, value: str) -> str:
        if value.startswith("postgres://"):
            return "postgresql+asyncpg://" + value[len("postgres://"):]
        if value.startswith("postgresql://"):
            return "postgresql+asyncpg://" + value[len("postgresql://"):]
        return value

    @property
    def is_testing(self) -> bool:
        return self.environment == "test"


@lru_cache
def get_settings() -> Settings:
    return Settings()
