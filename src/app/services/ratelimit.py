"""Redis-backed rate limiting. Pure service layer (no FastAPI).

Two primitives:
  * fixed-window counters (general per-minute + stricter SPARQL cap)
  * a concurrency gate (max in-flight generations per key)

All operations FAIL OPEN: if Redis is unavailable, the request is allowed rather than
erroring. Rate limiting is best-effort protection, never a hard dependency of the API.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from redis.asyncio import Redis
from redis.exceptions import RedisError

from ..core.logging import get_logger


@dataclass
class RateDecision:
    allowed: bool
    limit: int
    remaining: int
    retry_after: int  # seconds until the caller may retry


async def check_fixed_window(
    redis: Redis, *, scope: str, identity: str, limit: int, window_s: int = 60
) -> RateDecision:
    """Increment the current window's counter and decide. First hit sets the TTL.

    On any Redis error, fail open (allow)."""
    now = int(time.time())
    window = now // window_s
    key = f"rl:{scope}:{identity}:{window}"
    try:
        count = await redis.incr(key)
        if count == 1:
            await redis.expire(key, window_s)
    except RedisError as exc:
        get_logger().warning("ratelimit_redis_unavailable", scope=scope, error=str(exc))
        return RateDecision(True, limit, limit, 0)
    remaining = max(0, limit - count)
    if count > limit:
        retry_after = window_s - (now % window_s)
        return RateDecision(False, limit, 0, max(1, retry_after))
    return RateDecision(True, limit, remaining, 0)


async def acquire_slot(
    redis: Redis, *, scope: str, identity: str, limit: int, ttl_s: int = 3600
) -> bool:
    """Try to take one concurrency slot. Returns False if already at ``limit``.

    The counter carries a TTL so a crashed worker can't leak slots forever. On any Redis
    error, fail open (allow)."""
    key = f"conc:{scope}:{identity}"
    try:
        count = await redis.incr(key)
        if count == 1:
            await redis.expire(key, ttl_s)
        if count > limit:
            await redis.decr(key)
            return False
        return True
    except RedisError as exc:
        get_logger().warning("concurrency_redis_unavailable", scope=scope, error=str(exc))
        return True


async def release_slot(redis: Redis, *, scope: str, identity: str) -> None:
    key = f"conc:{scope}:{identity}"
    try:
        value = await redis.decr(key)
        if value < 0:
            # Never let the counter go negative (double-release / expiry races).
            await redis.set(key, 0)
    except RedisError:
        pass
