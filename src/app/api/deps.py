"""FastAPI dependencies. The API layer wires these; all logic lives in services/."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import Settings, get_settings
from ..core.errors import AppError
from ..db.session import get_session
from ..models import ApiKey
from ..services.auth import verify_api_key
from ..services.orkg.client import ORKGClient
from ..services.storage import StorageBackend, build_storage

SessionDep = Annotated[AsyncSession, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


async def require_api_key(
    session: SessionDep,
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
) -> ApiKey:
    if not x_api_key:
        raise AppError("unauthorized", "missing X-API-Key header", status=401)
    api_key = await verify_api_key(session, x_api_key)
    if api_key is None:
        raise AppError("unauthorized", "invalid or revoked API key", status=401)
    return api_key


ApiKeyDep = Annotated[ApiKey, Depends(require_api_key)]


def get_storage(settings: SettingsDep) -> StorageBackend:
    return build_storage(settings)


StorageDep = Annotated[StorageBackend, Depends(get_storage)]


def get_orkg_client(settings: SettingsDep) -> ORKGClient:
    return ORKGClient(
        oidc_url=settings.orkg_oidc_url,
        client_id=settings.orkg_client_id,
        api_url=settings.orkg_api_url,
    )


ORKGDep = Annotated[ORKGClient, Depends(get_orkg_client)]
