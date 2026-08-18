from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.exception_handlers import register_exception_handlers
from .api.middleware import request_context_middleware
from .api.v1 import auth, documents, health, models, orkg, reviews
from .config import Settings, get_settings
from .core.logging import configure_logging, get_logger
from .core.observability import init_sentry


@asynccontextmanager
async def lifespan(app: FastAPI):  # type: ignore[no-untyped-def]
    settings = get_settings()
    configure_logging(settings.log_level)
    init_sentry(
        settings.sentry_dsn,
        environment=settings.environment,
        traces_sample_rate=settings.sentry_traces_sample_rate,
    )
    get_logger().info("startup", environment=settings.environment, version=settings.app_version)
    yield
    get_logger().info("shutdown")


def _configure_cors(app: FastAPI, settings: Settings) -> None:
    origins = settings.cors_origins
    # Credentials cannot be combined with a wildcard origin (browsers reject it), so a
    # locked-down origin list unlocks cookie/Authorization sharing; "*" stays open+anon.
    allow_credentials = origins != ["*"]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=allow_credentials,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["x-request-id", "Retry-After"],
    )


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Literature Review Generator API",
        version=settings.app_version,
        summary="Generate structured, cited literature reviews from your sources.",
        description=(
            "Upload bibliographic sources (CSV/XLSX/PDF/JSON), generate a structured "
            "literature review as an async job, then preview and export it. "
            "Authenticate with an `X-API-Key` header."
        ),
        lifespan=lifespan,
    )

    _configure_cors(app, settings)
    app.middleware("http")(request_context_middleware)
    register_exception_handlers(app)

    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(documents.router)
    app.include_router(models.router)
    app.include_router(orkg.router)
    app.include_router(reviews.router)
    return app


app = create_app()
