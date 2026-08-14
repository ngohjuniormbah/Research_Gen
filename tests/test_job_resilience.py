"""Assurance that a broken/unreachable model config fails gracefully — the job is
marked failed with a recorded error, and the server never crashes."""

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Job, User
from app.models.job import JobStatus
from app.services.jobs import create_review_job, run_generate_review_job


async def _make_user(session: AsyncSession) -> User:
    user = User(email=f"resilience-{uuid.uuid4().hex}@example.com")
    session.add(user)
    await session.flush()
    return user


async def test_bad_provider_marks_job_failed_not_crash(session: AsyncSession) -> None:
    user = await _make_user(session)
    job = await create_review_job(
        session,
        user_id=user.id,
        payload={"topic": "x", "provider": "does-not-exist", "records": [{"title": "A"}]},
    )
    await session.commit()

    # The pipeline raises for the worker to see, but first records the failure durably.
    # An unknown provider surfaces as a KeyError from the registry.
    with pytest.raises(KeyError):
        await run_generate_review_job(session, job.id)

    refreshed = await session.get(Job, job.id)
    assert refreshed is not None
    assert refreshed.status == JobStatus.failed
    assert refreshed.error  # a human-readable reason is stored


async def test_missing_job_raises_cleanly(session: AsyncSession) -> None:
    with pytest.raises(ValueError):
        await run_generate_review_job(session, uuid.uuid4())
