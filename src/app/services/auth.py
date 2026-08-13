"""API-key issuing, verification and revocation. Pure service layer: no FastAPI."""

import hashlib
import secrets
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import ApiKey, User

KEY_PREFIX = "lrk_"


def _hash_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def generate_raw_key() -> str:
    return KEY_PREFIX + secrets.token_urlsafe(32)


async def get_or_create_user(session: AsyncSession, email: str, name: str = "") -> User:
    result = await session.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if user is None:
        user = User(email=email, name=name)
        session.add(user)
        await session.flush()
    return user


async def issue_api_key(
    session: AsyncSession, user: User, name: str = ""
) -> tuple[ApiKey, str]:
    """Create a key, persist only its hash, and return the plaintext once."""
    raw = generate_raw_key()
    api_key = ApiKey(
        user_id=user.id,
        name=name,
        key_hash=_hash_key(raw),
        prefix=raw[:12],
    )
    session.add(api_key)
    await session.flush()
    return api_key, raw


async def verify_api_key(session: AsyncSession, raw_key: str) -> ApiKey | None:
    """Return the active ApiKey for a plaintext key, or None if invalid/revoked."""
    if not raw_key or not raw_key.startswith(KEY_PREFIX):
        return None
    result = await session.execute(
        select(ApiKey).where(ApiKey.key_hash == _hash_key(raw_key))
    )
    api_key = result.scalar_one_or_none()
    if api_key is None or api_key.revoked_at is not None:
        return None
    api_key.last_used_at = datetime.now(UTC)
    return api_key


async def revoke_api_key(session: AsyncSession, api_key: ApiKey) -> None:
    api_key.revoked_at = datetime.now(UTC)
    await session.flush()
