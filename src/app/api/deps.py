"""FastAPI dependencies. The API layer wires these; all logic lives in services/."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import APIKeyHeader
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import Settings, get_settings
from ..core.crypto import TokenCipher
from ..core.errors import rate_limited, unauthorized
from ..core.redis import get_redis
from ..core.signing import TokenSigner
from ..db.session import get_session
from ..models import ApiKey
from ..services.auth import verify_api_key
from ..services.export import ExportRenderer, build_renderer
from ..services.orkg.client import ORKGClient
from ..services.orkg.tokens import DbTokenStore
from ..services.ratelimit import check_fixed_window
from ..services.storage import StorageBackend, build_storage

SessionDep = Annotated[AsyncSession, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


def get_redis_client() -> Redis:
    return get_redis()


RedisDep = Annotated[Redis, Depends(get_redis_client)]

# Registering this as a security scheme gives Swagger UI a single "Authorize" button
# that applies the key to every protected endpoint (instead of pasting it each time).
_api_key_scheme = APIKeyHeader(
    name="X-API-Key",
    auto_error=False,
    description="Paste the api_key returned by POST /api/v1/auth/api-keys",
)


async def require_api_key(
    request: Request,
    session: SessionDep,
    x_api_key: Annotated[str | None, Depends(_api_key_scheme)] = None,
) -> ApiKey:
    if not x_api_key:
        raise unauthorized("missing X-API-Key header")
    api_key = await verify_api_key(session, x_api_key)
    if api_key is None:
        raise unauthorized("invalid or revoked API key")
    # Surface the caller's key prefix to the access log (never the full key).
    request.state.key_prefix = api_key.prefix
    return api_key


ApiKeyDep = Annotated[ApiKey, Depends(require_api_key)]


async def _enforce_window(
    redis: Redis, settings: Settings, api_key: ApiKey, *, scope: str, limit: int
) -> None:
    if not settings.rate_limit_enabled:
        return
    decision = await check_fixed_window(
        redis, scope=scope, identity=str(api_key.id), limit=limit
    )
    if not decision.allowed:
        raise rate_limited(
            f"rate limit exceeded for {scope}; retry in {decision.retry_after}s",
            decision.retry_after,
        )


async def rate_limited_key(
    api_key: ApiKeyDep, redis: RedisDep, settings: SettingsDep
) -> ApiKey:
    """Authenticated caller subject to the general per-minute cap."""
    await _enforce_window(
        redis, settings, api_key, scope="general", limit=settings.rate_limit_per_minute
    )
    return api_key


async def sparql_rate_limited_key(
    api_key: ApiKeyDep, redis: RedisDep, settings: SettingsDep
) -> ApiKey:
    """Authenticated caller subject to the stricter SPARQL cap."""
    await _enforce_window(
        redis, settings, api_key, scope="sparql", limit=settings.sparql_rate_limit_per_minute
    )
    return api_key


RateLimitedKeyDep = Annotated[ApiKey, Depends(rate_limited_key)]
SparqlRateLimitedKeyDep = Annotated[ApiKey, Depends(sparql_rate_limited_key)]


def get_storage(settings: SettingsDep) -> StorageBackend:
    return build_storage(settings)


StorageDep = Annotated[StorageBackend, Depends(get_storage)]


def get_orkg_client(settings: SettingsDep, session: SessionDep) -> ORKGClient:
    # Durable token store bound to this request's DB session, so a user's ORKG
    # connection survives refreshes, new browser sessions, and backend redeploys.
    store = DbTokenStore(session, TokenCipher(settings.fernet_key))
    return ORKGClient(
        oidc_url=settings.orkg_oidc_url,
        client_id=settings.orkg_client_id,
        api_url=settings.orkg_api_url,
        token_store=store,
    )


ORKGDep = Annotated[ORKGClient, Depends(get_orkg_client)]


def get_renderer(settings: SettingsDep) -> ExportRenderer:
    return build_renderer(settings)


RendererDep = Annotated[ExportRenderer, Depends(get_renderer)]


def get_signer(settings: SettingsDep) -> TokenSigner:
    return TokenSigner(settings.export_url_secret)


SignerDep = Annotated[TokenSigner, Depends(get_signer)]
