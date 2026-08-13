from __future__ import annotations

import uuid

from fastapi import APIRouter, status

from ...core.errors import AppError
from ...models import Job, Review
from ...schemas.job import JobInfo
from ...schemas.review import ReviewCreate, ReviewOut
from ...services.jobs import create_review_job, run_generate_review_job
from ...services.llm.registry import get_registry
from ..deps import ApiKeyDep, SessionDep, SettingsDep

router = APIRouter(prefix="/api/v1/reviews", tags=["reviews"])


@router.post("", response_model=JobInfo, status_code=status.HTTP_202_ACCEPTED)
async def create_review(
    body: ReviewCreate,
    session: SessionDep,
    settings: SettingsDep,
    caller: ApiKeyDep,
) -> Job:
    """Submit a review generation job. Returns 202 with the Job; poll
    GET /reviews/jobs/{job_id} until it succeeds, then fetch the review."""
    if body.provider and body.provider not in get_registry().keys:
        raise AppError(
            "unknown_provider",
            f"provider '{body.provider}' is not registered",
            status=400,
            details=[{"available": get_registry().keys}],
        )
    payload = body.model_dump(mode="json")
    job = await create_review_job(session, user_id=caller.user_id, payload=payload)
    await session.commit()

    if settings.jobs_eager:
        await run_generate_review_job(session, job.id)
        refreshed = await session.get(Job, job.id)  # reflect final status/progress
        assert refreshed is not None
        return refreshed

    from ...worker.queue import enqueue_generate_review

    await enqueue_generate_review(job.id)
    return job


@router.get("/jobs/{job_id}", response_model=JobInfo)
async def get_job(job_id: uuid.UUID, session: SessionDep, caller: ApiKeyDep) -> Job:
    job = await session.get(Job, job_id)
    if job is None or job.user_id != caller.user_id:
        raise AppError("not_found", "job not found", status=404)
    return job


@router.get("/{review_id}", response_model=ReviewOut)
async def get_review(review_id: uuid.UUID, session: SessionDep, caller: ApiKeyDep) -> Review:
    review = await session.get(Review, review_id)
    if review is None or review.user_id != caller.user_id:
        raise AppError("not_found", "review not found", status=404)
    return review
