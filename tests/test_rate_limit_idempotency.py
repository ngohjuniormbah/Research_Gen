from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.config import get_settings
from app.models import User
from app.services import ratelimit


async def test_general_rate_limit_returns_429(app_factory, auth_headers) -> None:
    settings = get_settings().model_copy(update={"rate_limit_per_minute": 2})
    app = app_factory(settings)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r1 = await client.get("/api/v1/auth/api-keys", headers=auth_headers)
        r2 = await client.get("/api/v1/auth/api-keys", headers=auth_headers)
        r3 = await client.get("/api/v1/auth/api-keys", headers=auth_headers)
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r3.status_code == 429
    assert r3.json()["error"]["code"] == "rate_limited"
    assert "Retry-After" in r3.headers


async def test_sparql_has_stricter_limit(app_factory, auth_headers) -> None:
    settings = get_settings().model_copy(update={"sparql_rate_limit_per_minute": 1})
    app = app_factory(settings)
    transport = ASGITransport(app=app)
    # A guard-rejected query avoids any network call; the rate limiter runs first.
    body = {"query": "DROP GRAPH <g>"}
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        first = await client.post("/api/v1/orkg/sparql", headers=auth_headers, json=body)
        second = await client.post("/api/v1/orkg/sparql", headers=auth_headers, json=body)
    assert first.status_code == 400  # rejected by the SPARQL guard, limit not yet hit
    assert second.status_code == 429  # stricter cap of 1/min exceeded


async def test_generation_concurrency_cap(
    app_factory, api_key, auth_headers, sessionmaker, redis
) -> None:
    # Discover the caller's user id, then pre-take the only generation slot to simulate
    # an in-flight job. The next submit must be refused.
    async with sessionmaker() as s:
        user = (await s.execute(select(User))).scalars().first()
    assert user is not None
    identity = str(user.id)
    took = await ratelimit.acquire_slot(redis, scope="gen", identity=identity, limit=1)
    assert took

    settings = get_settings().model_copy(update={"max_concurrent_generations": 1})
    app = app_factory(settings)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/reviews", headers=auth_headers,
            json={"topic": "x", "records": [{"title": "A"}]},
        )
    assert resp.status_code == 429
    assert resp.json()["error"]["code"] == "rate_limited"


class _BoomRedis:
    """A Redis stand-in whose every op raises, to simulate an outage."""

    async def incr(self, *a, **k):
        from redis.exceptions import ConnectionError as RedisConnError

        raise RedisConnError("redis down")

    async def expire(self, *a, **k):
        from redis.exceptions import ConnectionError as RedisConnError

        raise RedisConnError("redis down")

    async def decr(self, *a, **k):
        from redis.exceptions import ConnectionError as RedisConnError

        raise RedisConnError("redis down")

    async def get(self, *a, **k):
        from redis.exceptions import ConnectionError as RedisConnError

        raise RedisConnError("redis down")

    async def set(self, *a, **k):
        from redis.exceptions import ConnectionError as RedisConnError

        raise RedisConnError("redis down")


async def test_ratelimit_fails_open_when_redis_down() -> None:
    boom = _BoomRedis()
    decision = await ratelimit.check_fixed_window(boom, scope="general", identity="x", limit=5)
    assert decision.allowed  # fail open, not error
    assert await ratelimit.acquire_slot(boom, scope="gen", identity="x", limit=1) is True


async def test_models_endpoint_survives_redis_outage(app_factory, auth_headers) -> None:
    from app.api.deps import get_redis_client

    app = app_factory()
    app.dependency_overrides[get_redis_client] = lambda: _BoomRedis()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/models", headers=auth_headers)
    assert resp.status_code == 200  # was 500 before fail-open
    assert "providers" in resp.json()


async def test_idempotency_key_dedupes(client: AsyncClient, auth_headers: dict) -> None:
    body = {"topic": "idempotent topic", "records": [{"title": "A"}]}
    headers = {**auth_headers, "Idempotency-Key": "abc-123"}
    r1 = await client.post("/api/v1/reviews", headers=headers, json=body)
    r2 = await client.post("/api/v1/reviews", headers=headers, json=body)
    assert r1.status_code == 202
    assert r2.status_code == 202
    assert r1.json()["id"] == r2.json()["id"]  # same job, no double-generate


async def test_different_idempotency_key_new_job(client: AsyncClient, auth_headers: dict) -> None:
    body = {"topic": "t", "records": [{"title": "A"}]}
    r1 = await client.post(
        "/api/v1/reviews", headers={**auth_headers, "Idempotency-Key": "k1"}, json=body
    )
    r2 = await client.post(
        "/api/v1/reviews", headers={**auth_headers, "Idempotency-Key": "k2"}, json=body
    )
    assert r1.json()["id"] != r2.json()["id"]


async def test_rate_limit_can_be_disabled(app_factory, auth_headers) -> None:
    settings = get_settings().model_copy(
        update={"rate_limit_enabled": False, "rate_limit_per_minute": 1}
    )
    app = app_factory(settings)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        for _ in range(5):
            resp = await client.get("/api/v1/auth/api-keys", headers=auth_headers)
            assert resp.status_code == 200
