"""Review export pipeline. md/docx are cheap enough to render inline; pdf runs as a
worker job that stores the file and hands back a signed, temporary download URL."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from ..core.signing import TokenSigner
from ..models import Job, Review
from ..models.job import JobStatus
from .export import ExportRenderer, content_type_for
from .storage import StorageBackend

EXPORT_DOWNLOAD_PATH = "/api/v1/reviews/exports"


def render_review_export(
    review: Review, fmt: str, renderer: ExportRenderer
) -> tuple[bytes, str, str]:
    """Render a review to bytes. Returns (data, content_type, filename)."""
    data = renderer.render(review.content_md, fmt, title=review.topic or "Literature Review")
    filename = f"review-{review.id}.{fmt}"
    return data, content_type_for(fmt), filename


async def create_export_job(
    session: AsyncSession, *, user_id: uuid.UUID, review_id: uuid.UUID, fmt: str
) -> Job:
    job = Job(
        user_id=user_id,
        kind="export_review",
        status=JobStatus.queued,
        input={"review_id": str(review_id), "format": fmt},
    )
    session.add(job)
    await session.flush()
    return job


async def run_export_job(
    session: AsyncSession,
    storage: StorageBackend,
    renderer: ExportRenderer,
    signer: TokenSigner,
    *,
    job_id: uuid.UUID,
    url_ttl_s: int,
) -> Job:
    job = await session.get(Job, job_id)
    if job is None:
        raise ValueError(f"job {job_id} not found")
    try:
        job.status = JobStatus.running
        job.progress = 20
        await session.flush()

        payload = job.input or {}
        review = await session.get(Review, uuid.UUID(str(payload["review_id"])))
        if review is None or review.user_id != job.user_id:
            raise ValueError("review not found")

        data, content_type, filename = render_review_export(
            review, str(payload["format"]), renderer
        )
        job.progress = 60
        await session.flush()

        storage_key = await storage.put(data, filename=filename)
        token = signer.sign(
            {"sk": storage_key, "ct": content_type, "fn": filename}, ttl_s=url_ttl_s
        )
        result: dict[str, Any] = {
            "format": payload["format"],
            "content_type": content_type,
            "filename": filename,
            "storage_key": storage_key,
            "download_url": f"{EXPORT_DOWNLOAD_PATH}/{token}",
        }
        job.result = result
        job.status = JobStatus.succeeded
        job.progress = 100
        await session.commit()
        return job
    except Exception as exc:  # noqa: BLE001 - persist failure, then re-raise
        await session.rollback()
        job = await session.get(Job, job_id)
        if job is not None:
            job.status = JobStatus.failed
            job.error = str(exc)[:2000]
            await session.commit()
        raise
