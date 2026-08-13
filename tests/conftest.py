import os
import tempfile
from collections.abc import AsyncIterator

# Configure the app for tests BEFORE importing anything that reads settings.
os.environ["ENVIRONMENT"] = "test"
os.environ["JOBS_EAGER"] = "true"
os.environ["LLM_DEFAULT_PROVIDER"] = "fake"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite://"
os.environ["STORAGE_LOCAL_DIR"] = tempfile.mkdtemp(prefix="litreview-test-")

import pytest  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy.ext.asyncio import (  # noqa: E402
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.db.session import get_session  # noqa: E402
from app.main import create_app  # noqa: E402
from app.services import auth as auth_service  # noqa: E402

get_settings.cache_clear()


@pytest.fixture
async def sessionmaker() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    # A single in-memory SQLite connection (StaticPool) shared for the test's lifetime.
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    yield maker
    await engine.dispose()


@pytest.fixture
async def session(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    async with sessionmaker() as s:
        yield s


@pytest.fixture
async def client(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncClient]:
    app = create_app()

    async def _override_get_session() -> AsyncIterator[AsyncSession]:
        async with sessionmaker() as s:
            yield s

    app.dependency_overrides[get_session] = _override_get_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
async def api_key(sessionmaker: async_sessionmaker[AsyncSession]) -> str:
    """Issue a real API key and return the plaintext for use in request headers."""
    async with sessionmaker() as s:
        user = await auth_service.get_or_create_user(s, "tester@example.com", "Tester")
        _, raw = await auth_service.issue_api_key(s, user, "test-key")
        await s.commit()
    return raw


@pytest.fixture
def auth_headers(api_key: str) -> dict[str, str]:
    return {"X-API-Key": api_key}
