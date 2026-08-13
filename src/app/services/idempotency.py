"""Idempotency-Key support for POST /reviews. A retried submit with the same key (per
API key) returns the original job instead of generating a second review."""

from __future__ import annotations

from redis.asyncio import Redis


def _key(identity: str, idempotency_key: str) -> str:
    return f"idem:{identity}:{idempotency_key}"


async def lookup(redis: Redis, *, identity: str, idempotency_key: str) -> str | None:
    """Return the job id previously created for this key, if any."""
    return await redis.get(_key(identity, idempotency_key))


async def remember(
    redis: Redis, *, identity: str, idempotency_key: str, job_id: str, ttl_s: int
) -> None:
    await redis.set(_key(identity, idempotency_key), job_id, ex=ttl_s)
