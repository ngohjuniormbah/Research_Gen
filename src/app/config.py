from functools import lru_cache

from pydantic import BaseModel, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class ProviderConfig(BaseModel):
    """One entry in the config-driven LLM registry.

    Adding a selectable model = one entry here (or in the LLM_PROVIDERS env var),
    zero code change. Each real provider is an OpenAI-compatible endpoint served by
    Ollama (local) or a hosted service.
    """

    base_url: str = ""
    model: str = ""
    api_key: str = ""
    # "openai" -> OpenAI-compatible HTTP client; "fake" -> deterministic in-process.
    kind: str = "openai"


def _default_providers() -> dict[str, ProviderConfig]:
    """Sensible defaults so the registry works out of the box against local Ollama.

    Every entry is overridable via the LLM_PROVIDERS env var. The `fake` provider is
    always present and needs no network or API key; it is the default used by tests.
    """
    ollama = "http://localhost:11434/v1"
    return {
        "fake": ProviderConfig(kind="fake", model="fake-1"),
        "gemma": ProviderConfig(base_url=ollama, model="gemma2"),
        "qwen": ProviderConfig(base_url=ollama, model="qwen2.5"),
        "deepseek-v4": ProviderConfig(base_url=ollama, model="deepseek-v4"),
        "glm": ProviderConfig(base_url=ollama, model="glm4"),
    }


class Settings(BaseSettings):
    """Typed application configuration. Every env var lives here, nowhere else."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "litreview-backend"
    app_version: str = "0.3.0"
    environment: str = "development"
    log_level: str = "INFO"

    # JSON list in env; locked to the frontend origin(s) in staging/production.
    # e.g. CORS_ORIGINS='["https://app.example.com"]'
    cors_origins: list[str] = ["*"]

    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/litreview"
    redis_url: str = "redis://localhost:6379/0"

    # --- Observability ---
    # Empty DSN => Sentry is a no-op. Traces sampling defaults to off.
    sentry_dsn: str = ""
    sentry_traces_sample_rate: float = 0.0

    # --- Security / secrets ---
    # Fernet key (urlsafe base64, 32 bytes) used to encrypt ORKG tokens at rest.
    # Empty => tokens are stored in-process unencrypted (dev only). Generate with:
    #   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    fernet_key: str = ""
    # HMAC secret for signing temporary export download URLs.
    export_url_secret: str = "dev-insecure-change-me"
    export_url_ttl_s: int = 900

    # --- Validation limits ---
    max_upload_bytes: int = 10_000_000  # 10 MB
    max_source_records: int = 500
    max_topic_chars: int = 1000

    # --- Export / rendering ---
    # "pandoc" (real, needs the pandoc binary) or "fake" (deterministic bytes for tests).
    export_renderer: str = "pandoc"
    pandoc_pdf_engine: str = "weasyprint"

    # --- Rate limiting (Redis, per API key) ---
    rate_limit_enabled: bool = True
    rate_limit_per_minute: int = 60  # general cap across authenticated endpoints
    max_concurrent_generations: int = 3  # in-flight generation jobs per key
    sparql_rate_limit_per_minute: int = 10  # stricter cap for SPARQL

    # --- Idempotency ---
    idempotency_ttl_s: int = 86_400  # 24h

    # --- Storage (Step 2: local FS in dev, interface allows S3/MinIO later) ---
    storage_backend: str = "local"  # "local"
    storage_local_dir: str = "./data/uploads"
    # MinIO / S3-compatible knobs (wired via StorageBackend interface).
    s3_endpoint_url: str = ""
    s3_bucket: str = "litreview"
    s3_access_key: str = ""
    s3_secret_key: str = ""

    # --- LLM registry ---
    # Override/extend the registry entirely from env, e.g.:
    #   LLM_PROVIDERS='{"gemma": {"base_url": "...", "model": "gemma2", "api_key": "..."}}'
    llm_providers: dict[str, ProviderConfig] = Field(default_factory=_default_providers)
    llm_default_provider: str = "fake"
    llm_max_context_tokens: int = 8000
    llm_request_timeout_s: float = 120.0

    # --- OpenAI (paid ChatGPT) convenience ---
    # Set OPENAI_API_KEY to auto-register an "openai" provider (no LLM_PROVIDERS JSON
    # needed). Select it with LLM_DEFAULT_PROVIDER=openai or provider:"openai" per request.
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    openai_base_url: str = "https://api.openai.com/v1"

    # When true, generation runs inline in the request instead of via the arq worker.
    # Used by tests/dev so the pipeline is exercised without a live Redis+worker.
    jobs_eager: bool = False

    # --- ORKG integration ---
    orkg_oidc_url: str = "https://accounts.orkg.org/realms/orkg"
    orkg_client_id: str = "orkg-client"
    orkg_api_url: str = "https://orkg.org/api"
    orkg_sparql_url: str = "https://orkg.org/triplestore"
    orkg_sparql_max_limit: int = 500
    orkg_sparql_timeout_s: float = 30.0

    @model_validator(mode="after")
    def _register_openai_provider(self) -> "Settings":
        """If an OpenAI key is provided, add a ready-to-use 'openai' provider entry so
        paid ChatGPT works with zero code changes — just set the key (and select it)."""
        if self.openai_api_key and "openai" not in self.llm_providers:
            self.llm_providers["openai"] = ProviderConfig(
                base_url=self.openai_base_url,
                model=self.openai_model,
                api_key=self.openai_api_key,
                kind="openai",
            )
        return self

    @field_validator("database_url")
    @classmethod
    def _force_async_driver(cls, value: str) -> str:
        """Managed Postgres (Railway/Render/Heroku) hands out ``postgres://`` or
        ``postgresql://`` URLs, but this app needs the asyncpg driver. Rewrite the scheme
        so the platform's injected URL works as-is."""
        if value.startswith("postgres://"):
            return "postgresql+asyncpg://" + value[len("postgres://") :]
        if value.startswith("postgresql://"):
            return "postgresql+asyncpg://" + value[len("postgresql://") :]
        return value

    @property
    def is_testing(self) -> bool:
        return self.environment == "test"


@lru_cache
def get_settings() -> Settings:
    return Settings()
