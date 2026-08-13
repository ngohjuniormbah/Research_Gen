"""arq worker configuration. Run with:  arq app.worker.settings.WorkerSettings"""

from __future__ import annotations

import uuid
from typing import Any

from arq.connections import RedisSettings

from ..config import get_settings
from ..core.logging import configure_logging, get_logger
from ..db.session import dispose_engine, get_sessionmaker
from ..services.jobs import run_generate_review_job


async def generate_review(ctx: dict[str, Any], job_id: str) -> str:
    """arq task: run the generate-review pipeline for a persisted Job row."""
    async with get_sessionmaker()() as session:
        review = await run_generate_review_job(session, uuid.UUID(job_id))
    get_logger().info("generate_review.done", job_id=job_id, review_id=str(review.id))
    return str(review.id)


async def on_startup(ctx: dict[str, Any]) -> None:
    configure_logging(get_settings().log_level)
    get_logger().info("worker.startup")


async def on_shutdown(ctx: dict[str, Any]) -> None:
    await dispose_engine()
    get_logger().info("worker.shutdown")


class WorkerSettings:
    functions = [generate_review]
    on_startup = on_startup
    on_shutdown = on_shutdown
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
