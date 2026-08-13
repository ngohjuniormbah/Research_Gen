"""Job lifecycle + the generate-review pipeline as run against the database.

This is the seam between the worker (which owns a session) and the pure orchestration
in ``review.py``. It updates the first-class Job row (status/progress) as it goes."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Document, Job, Review
from ..models.job import JobStatus
from ..schemas.source_record import SourceRecord
from .ingestion.normalize import normalize_records
from .llm.registry import get_registry
from .review import generate_review_content


async def create_review_job(
    session: AsyncSession, *, user_id: uuid.UUID, payload: dict[str, Any]
) -> Job:
    job = Job(
        user_id=user_id,
        kind="generate_review",
        status=JobStatus.queued,
        input=payload,
    )
    session.add(job)
    await session.flush()
    return job


async def _gather_records(
    session: AsyncSession, *, user_id: uuid.UUID, payload: dict[str, Any]
) -> list[SourceRecord]:
    records: list[SourceRecord] = [
        SourceRecord.model_validate(r) for r in payload.get("records", [])
    ]
    doc_ids = [uuid.UUID(str(d)) for d in payload.get("document_ids", [])]
    if doc_ids:
        result = await session.execute(
            select(Document).where(
                Document.id.in_(doc_ids), Document.user_id == user_id
            )
        )
        for doc in result.scalars():
            for raw in doc.parsed_meta.get("records", []):
                records.append(SourceRecord.model_validate(raw))
    return normalize_records(records)


async def run_generate_review_job(session: AsyncSession, job_id: uuid.UUID) -> Review:
    """Execute one generation job end to end, updating progress and persisting a
    Review. Commits on success and on failure so the job status is always durable."""
    job = await session.get(Job, job_id)
    if job is None:
        raise ValueError(f"job {job_id} not found")

    try:
        job.status = JobStatus.running
        job.progress = 10
        await session.flush()

        payload = job.input or {}
        records = await _gather_records(session, user_id=job.user_id, payload=payload)
        job.progress = 40
        await session.flush()

        provider = get_registry().get(payload.get("provider"))
        result = await generate_review_content(
            provider=provider,
            topic=str(payload.get("topic", "")),
            records=records,
            token_budget=get_registry().settings.llm_max_context_tokens,
            max_tokens=int(payload.get("max_tokens") or 1500),
        )
        job.progress = 80
        await session.flush()

        review = Review(
            user_id=job.user_id,
            job_id=job.id,
            topic=str(payload.get("topic", "")),
            provider=result.provider,
            model=result.model,
            content_md=result.content_md,
            structured=result.structured,
        )
        session.add(review)
        await session.flush()

        job.status = JobStatus.succeeded
        job.progress = 100
        job.result = {"review_id": str(review.id)}
        await session.commit()
        return review
    except Exception as exc:  # noqa: BLE001 - persist failure, then re-raise
        await session.rollback()
        job = await session.get(Job, job_id)
        if job is not None:
            job.status = JobStatus.failed
            job.error = str(exc)[:2000]
            await session.commit()
        raise
