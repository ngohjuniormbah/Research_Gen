"""arq worker configuration. Run with:  arq app.worker.settings.WorkerSettings"""

from __future__ import annotations

import uuid
from typing import Any

from arq.connections import RedisSettings

from ..config import get_settings
from ..core.crypto import TokenCipher  # noqa: F401  (ensures cipher module imports cleanly)
from ..core.logging import configure_logging, get_logger
from ..core.redis import close_redis, get_redis
from ..core.signing import TokenSigner
from ..db.session import dispose_engine, get_sessionmaker
from ..models import Job
from ..services import ratelimit
from ..services.export import build_renderer
from ..services.exports import run_export_job
from ..services.jobs import run_generate_review_job
from ..services.storage import build_storage

_GEN_SCOPE = "gen"


async def generate_review(ctx: dict[str, Any], job_id: str) -> str:
    """arq task: run the generate-review pipeline, then release the concurrency slot."""
    jid = uuid.UUID(job_id)
    identity: str | None = None
    try:
        async with get_sessionmaker()() as session:
            job = await session.get(Job, jid)
            identity = str(job.user_id) if job else None
            review = await run_generate_review_job(session, jid)
        get_logger().info("generate_review.done", job_id=job_id, review_id=str(review.id))
        return str(review.id)
    finally:
        if identity:
            await ratelimit.release_slot(get_redis(), scope=_GEN_SCOPE, identity=identity)


async def export_review(ctx: dict[str, Any], job_id: str) -> str:
    """arq task: render a review export (pdf), store it, sign a temporary URL."""
    settings = get_settings()
    storage = build_storage(settings)
    renderer = build_renderer(settings)
    signer = TokenSigner(settings.export_url_secret)
    async with get_sessionmaker()() as session:
        job = await run_export_job(
            session, storage, renderer, signer,
            job_id=uuid.UUID(job_id), url_ttl_s=settings.export_url_ttl_s,
        )
    get_logger().info("export_review.done", job_id=job_id)
    return str(job.id)


async def on_startup(ctx: dict[str, Any]) -> None:
    configure_logging(get_settings().log_level)
    get_logger().info("worker.startup")


async def on_shutdown(ctx: dict[str, Any]) -> None:
    await dispose_engine()
    await close_redis()
    get_logger().info("worker.shutdown")


class WorkerSettings:
    functions = [generate_review, export_review]
    on_startup = on_startup
    on_shutdown = on_shutdown
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
