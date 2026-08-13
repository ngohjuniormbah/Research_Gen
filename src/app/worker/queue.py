"""Thin helpers to enqueue jobs onto arq's Redis queue from the API process."""

from __future__ import annotations

import uuid

from arq import create_pool
from arq.connections import ArqRedis, RedisSettings

from ..config import get_settings


async def get_arq_pool() -> ArqRedis:
    return await create_pool(RedisSettings.from_dsn(get_settings().redis_url))


async def enqueue_generate_review(job_id: uuid.UUID) -> None:
    pool = await get_arq_pool()
    try:
        await pool.enqueue_job("generate_review", str(job_id))
    finally:
        await pool.close()


async def enqueue_export_review(job_id: uuid.UUID) -> None:
    pool = await get_arq_pool()
    try:
        await pool.enqueue_job("export_review", str(job_id))
    finally:
        await pool.close()
