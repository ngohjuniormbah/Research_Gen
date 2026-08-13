from __future__ import annotations

import uuid

from fastapi import APIRouter, status
from sqlalchemy import select

from ...core.errors import AppError
from ...models import ApiKey
from ...schemas.auth import ApiKeyCreate, ApiKeyCreated, ApiKeyInfo
from ...services import auth as auth_service
from ..deps import ApiKeyDep, SessionDep

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/api-keys", response_model=ApiKeyCreated, status_code=status.HTTP_201_CREATED)
async def create_api_key(body: ApiKeyCreate, session: SessionDep) -> ApiKeyCreated:
    """Bootstrap endpoint: create (or reuse) a user and issue a new API key.

    The plaintext key is returned exactly once — store it now."""
    user = await auth_service.get_or_create_user(session, str(body.email), body.name)
    api_key, raw = await auth_service.issue_api_key(session, user, body.name)
    await session.commit()
    return ApiKeyCreated(
        id=api_key.id,
        name=api_key.name,
        prefix=api_key.prefix,
        revoked_at=api_key.revoked_at,
        last_used_at=api_key.last_used_at,
        created_at=api_key.created_at,
        api_key=raw,
    )


@router.get("/api-keys", response_model=list[ApiKeyInfo])
async def list_api_keys(session: SessionDep, caller: ApiKeyDep) -> list[ApiKey]:
    result = await session.execute(
        select(ApiKey).where(ApiKey.user_id == caller.user_id).order_by(ApiKey.created_at)
    )
    return list(result.scalars())


@router.delete("/api-keys/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_api_key(key_id: uuid.UUID, session: SessionDep, caller: ApiKeyDep) -> None:
    api_key = await session.get(ApiKey, key_id)
    if api_key is None or api_key.user_id != caller.user_id:
        raise AppError("not_found", "API key not found", status=404)
    await auth_service.revoke_api_key(session, api_key)
    await session.commit()
