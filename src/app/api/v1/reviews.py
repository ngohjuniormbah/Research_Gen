from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Header, Query, Response, status

from ...core.errors import AppError, ErrorCode, not_found, rate_limited
from ...core.signing import SignatureError
from ...models import Job, Review
from ...schemas.job import JobInfo
from ...schemas.review import PreviewOut, ReviewCreate, ReviewOut
from ...services import idempotency, ratelimit
from ...services.export import EXPORT_FORMATS
from ...services.exports import create_export_job, render_review_export, run_export_job
from ...services.jobs import create_review_job, run_generate_review_job
from ...services.llm.registry import get_registry
from ...services.render import markdown_to_html
from ..deps import (
    RateLimitedKeyDep,
    RedisDep,
    RendererDep,
    SessionDep,
    SettingsDep,
    SignerDep,
    StorageDep,
)

router = APIRouter(prefix="/api/v1/reviews", tags=["reviews"])

_GEN_SCOPE = "gen"


async def _load_review(session: SessionDep, review_id: uuid.UUID, user_id: uuid.UUID) -> Review:
    review = await session.get(Review, review_id)
    if review is None or review.user_id != user_id:
        raise not_found("review not found")
    return review


@router.post(
    "",
    response_model=JobInfo,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Submit a review generation job",
    description=(
        "Enqueues an async generation job and returns **202** with the job. Poll "
        "`GET /reviews/jobs/{job_id}` until `status` is `succeeded`, then fetch the "
        "review via its `result.review_id`. Pass an optional `Idempotency-Key` header "
        "so a retried submit does not double-generate."
    ),
)
async def create_review(
    body: ReviewCreate,
    session: SessionDep,
    settings: SettingsDep,
    redis: RedisDep,
    caller: RateLimitedKeyDep,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> Job:
    if body.provider and body.provider not in get_registry().keys:
        raise AppError(
            ErrorCode.UNKNOWN_PROVIDER,
            f"provider '{body.provider}' is not registered",
            status=400,
            details=[{"available": get_registry().keys}],
        )

    identity = str(caller.user_id)
    if idempotency_key:
        existing = await idempotency.lookup(
            redis, identity=identity, idempotency_key=idempotency_key
        )
        if existing:
            job = await session.get(Job, uuid.UUID(existing))
            if job is not None:
                return job

    # Concurrency gate: cap in-flight generations per key.
    acquired = False
    if settings.rate_limit_enabled:
        if not await ratelimit.acquire_slot(
            redis, scope=_GEN_SCOPE, identity=identity,
            limit=settings.max_concurrent_generations,
        ):
            raise rate_limited(
                f"too many concurrent generations (max {settings.max_concurrent_generations})", 5
            )
        acquired = True

    payload = body.model_dump(mode="json")
    job = await create_review_job(session, user_id=caller.user_id, payload=payload)
    await session.commit()
    if idempotency_key:
        await idempotency.remember(
            redis,
            identity=identity,
            idempotency_key=idempotency_key,
            job_id=str(job.id),
            ttl_s=settings.idempotency_ttl_s,
        )

    if settings.jobs_eager:
        try:
            await run_generate_review_job(session, job.id)
        finally:
            if acquired:
                await ratelimit.release_slot(redis, scope=_GEN_SCOPE, identity=identity)
        refreshed = await session.get(Job, job.id)
        assert refreshed is not None
        return refreshed

    from ...worker.queue import enqueue_generate_review

    await enqueue_generate_review(job.id)
    return job


@router.get("/jobs/{job_id}", response_model=JobInfo, summary="Poll a job's status")
async def get_job(job_id: uuid.UUID, session: SessionDep, caller: RateLimitedKeyDep) -> Job:
    job = await session.get(Job, job_id)
    if job is None or job.user_id != caller.user_id:
        raise not_found("job not found")
    return job


@router.get(
    "/exports/{token}",
    summary="Download a signed export",
    description="Public, time-limited download for an export produced by a PDF export job. "
    "The signed token embeds the storage key and expiry; no API key is required.",
)
async def download_export(token: str, storage: StorageDep, signer: SignerDep) -> Response:
    try:
        payload = signer.verify(token)
    except SignatureError as exc:
        raise AppError(
            ErrorCode.UNAUTHORIZED, f"invalid download token: {exc}", status=401
        ) from exc
    try:
        data = await storage.get(str(payload["sk"]))
    except (FileNotFoundError, ValueError) as exc:
        raise not_found("export file not found") from exc
    filename = str(payload.get("fn", "export"))
    return Response(
        content=data,
        media_type=str(payload.get("ct", "application/octet-stream")),
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{review_id}", response_model=ReviewOut, summary="Fetch a completed review")
async def get_review(
    review_id: uuid.UUID, session: SessionDep, caller: RateLimitedKeyDep
) -> Review:
    return await _load_review(session, review_id, caller.user_id)


@router.get(
    "/{review_id}/preview",
    response_model=PreviewOut,
    summary="Render a sanitized HTML preview",
    description="Converts the review's canonical Markdown to sanitized HTML "
    "(scripts/handlers/`javascript:` URLs are stripped).",
)
async def preview_review(
    review_id: uuid.UUID,
    session: SessionDep,
    caller: RateLimitedKeyDep,
    format: str = Query("html", pattern="^(html)$"),
) -> PreviewOut:
    review = await _load_review(session, review_id, caller.user_id)
    return PreviewOut(id=review.id, format=format, html=markdown_to_html(review.content_md))


@router.get(
    "/{review_id}/export",
    summary="Export a review (md/docx inline, pdf async)",
    description="`md` and `docx` stream back inline. `pdf` is slow, so it runs as a "
    "worker job: this returns **202** with a job; poll it, then use "
    "`result.download_url` (a signed, temporary URL).",
)
async def export_review(
    review_id: uuid.UUID,
    session: SessionDep,
    settings: SettingsDep,
    storage: StorageDep,
    renderer: RendererDep,
    signer: SignerDep,
    caller: RateLimitedKeyDep,
    format: str = Query("pdf"),
) -> Response:
    if format not in EXPORT_FORMATS:
        raise AppError(
            ErrorCode.VALIDATION,
            f"unsupported export format '{format}'",
            status=422,
            details=[{"field": "format", "allowed": list(EXPORT_FORMATS)}],
        )
    review = await _load_review(session, review_id, caller.user_id)

    # md/docx are cheap: render inline.
    if format in ("md", "docx"):
        data, content_type, filename = render_review_export(review, format, renderer)
        return Response(
            content=data,
            media_type=content_type,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    # pdf: async export job.
    job = await create_export_job(
        session, user_id=caller.user_id, review_id=review.id, fmt=format
    )
    await session.commit()
    if settings.jobs_eager:
        await run_export_job(
            session, storage, renderer, signer,
            job_id=job.id, url_ttl_s=settings.export_url_ttl_s,
        )
        refreshed = await session.get(Job, job.id)
        assert refreshed is not None
        return Response(
            content=JobInfo.model_validate(refreshed).model_dump_json(),
            media_type="application/json",
            status_code=status.HTTP_202_ACCEPTED,
        )

    from ...worker.queue import enqueue_export_review

    await enqueue_export_review(job.id)
    return Response(
        content=JobInfo.model_validate(job).model_dump_json(),
        media_type="application/json",
        status_code=status.HTTP_202_ACCEPTED,
    )
