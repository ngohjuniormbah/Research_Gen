"""Idempotency-Key support for POST /reviews. A retried submit with the same key (per
API key) returns the original job instead of generating a second review.

Fails open: if Redis is unavailable, dedup is simply skipped (never errors the request)."""

from __future__ import annotations

from redis.asyncio import Redis
from redis.exceptions import RedisError

from ..core.logging import get_logger


def _key(identity: str, idempotency_key: str) -> str:
    return f"idem:{identity}:{idempotency_key}"


async def lookup(redis: Redis, *, identity: str, idempotency_key: str) -> str | None:
    """Return the job id previously created for this key, if any."""
    try:
        return await redis.get(_key(identity, idempotency_key))
    except RedisError as exc:
        get_logger().warning("idempotency_redis_unavailable", error=str(exc))
        return None


async def remember(
    redis: Redis, *, identity: str, idempotency_key: str, job_id: str, ttl_s: int
) -> None:
    try:
        await redis.set(_key(identity, idempotency_key), job_id, ex=ttl_s)
    except RedisError as exc:
        get_logger().warning("idempotency_redis_unavailable", error=str(exc))
