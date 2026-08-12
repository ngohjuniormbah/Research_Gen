from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed application configuration. Every env var lives here, nowhere else."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "litreview-backend"
    environment: str = "development"
    log_level: str = "INFO"

    # Comma/JSON list in env; locked down to the frontend origin in staging.
    cors_origins: list[str] = ["*"]

    # Wired into real dependencies in later slices.
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/litreview"
    redis_url: str = "redis://localhost:6379/0"


@lru_cache
def get_settings() -> Settings:
    return Settings()
