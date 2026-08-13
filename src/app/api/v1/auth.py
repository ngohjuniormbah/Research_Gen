from __future__ import annotations

import uuid

from fastapi import APIRouter, status
from sqlalchemy import select

from ...core.errors import not_found
from ...models import ApiKey
from ...schemas.auth import ApiKeyCreate, ApiKeyCreated, ApiKeyInfo
from ...services import auth as auth_service
from ..deps import RateLimitedKeyDep, SessionDep

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post(
    "/api-keys",
    response_model=ApiKeyCreated,
    status_code=status.HTTP_201_CREATED,
    summary="Issue an API key (bootstrap)",
    description="Create (or reuse) a user by email and issue a new API key. The "
    "plaintext `api_key` is returned **exactly once** — store it now.",
)
async def create_api_key(body: ApiKeyCreate, session: SessionDep) -> ApiKeyCreated:
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


@router.get("/api-keys", response_model=list[ApiKeyInfo], summary="List your API keys")
async def list_api_keys(session: SessionDep, caller: RateLimitedKeyDep) -> list[ApiKey]:
    result = await session.execute(
        select(ApiKey).where(ApiKey.user_id == caller.user_id).order_by(ApiKey.created_at)
    )
    return list(result.scalars())


@router.delete(
    "/api-keys/{key_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke an API key",
)
async def revoke_api_key(
    key_id: uuid.UUID, session: SessionDep, caller: RateLimitedKeyDep
) -> None:
    api_key = await session.get(ApiKey, key_id)
    if api_key is None or api_key.user_id != caller.user_id:
        raise not_found("API key not found")
    await auth_service.revoke_api_key(session, api_key)
    await session.commit()
