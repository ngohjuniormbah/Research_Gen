from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Header, Query, Response, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from ...core.errors import AppError, ErrorCode, not_found, rate_limited
from ...core.signing import SignatureError
from ...models import Job, Review
from ...schemas.job import JobInfo
from ...schemas.review import (
    MultiReviewCreate,
    MultiReviewItem,
    MultiReviewOut,
    PreviewOut,
    ReviewCreate,
    ReviewOut,
    ReviewSummary,
    ReviewUpdate,
)
from ...services import idempotency, ratelimit
from ...services.citations import to_csl_json
from ...services.export import EXPORT_FORMATS
from ...services.exports import create_export_job, render_review_export, run_export_job
from ...services.jobs import _gather_records, create_review_job, run_generate_review_job
from ...services.llm.registry import get_registry
from ...services.render import markdown_to_html
from ...services.review import (
    ReviewResult,
    finalize_review,
    generate_review_content,
    prepare_review,
)
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


@router.get(
    "",
    response_model=list[ReviewSummary],
    summary="List the caller's reviews (past work)",
    description="Returns the caller's reviews newest-first as compact summaries for the "
    "'past work' list. Supports a simple text search over the topic and pagination.",
)
async def list_reviews(
    session: SessionDep,
    caller: RateLimitedKeyDep,
    q: str | None = Query(None, description="Case-insensitive search over the topic."),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> list[ReviewSummary]:
    stmt = select(Review).where(Review.user_id == caller.user_id)
    if q and q.strip():
        stmt = stmt.where(Review.topic.ilike(f"%{q.strip()}%"))
    stmt = stmt.order_by(Review.created_at.desc()).limit(limit).offset(offset)
    rows = (await session.execute(stmt)).scalars().all()
    return [
        ReviewSummary(
            id=r.id, topic=r.topic, provider=r.provider, model=r.model,
            created_at=r.created_at,
            sections=len((r.structured or {}).get("sections", []) or []),
        )
        for r in rows
    ]


def _sse(payload: dict[str, object]) -> str:
    return f"data: {json.dumps(payload)}\n\n"


@router.post(
    "/stream",
    summary="Generate a review with live token streaming (SSE)",
    description="Server-Sent Events stream of the generation: `{type:'token'}` events as "
    "text is produced, then a final `{type:'done', review_id, ...}` once the review is "
    "persisted, or `{type:'error'}` on failure. Powers the ChatGPT-style live output.",
)
async def stream_review(
    body: ReviewCreate,
    session: SessionDep,
    caller: RateLimitedKeyDep,
) -> StreamingResponse:
    if body.provider and body.provider not in get_registry().keys:
        raise AppError(
            ErrorCode.UNKNOWN_PROVIDER,
            f"provider '{body.provider}' is not registered",
            status=400,
            details=[{"available": get_registry().keys}],
        )
    payload = body.model_dump(mode="json")

    async def gen() -> AsyncIterator[str]:
        try:
            records = await _gather_records(session, user_id=caller.user_id, payload=payload)
            provider = get_registry().get(body.provider)
            prepared = await prepare_review(
                provider=provider,
                topic=body.topic,
                records=records,
                instructions=body.instructions or "",
                token_budget=get_registry().settings.llm_max_context_tokens,
            )
            content = ""
            async for tok in provider.stream(
                prepared.messages, max_tokens=int(body.max_tokens or 1500)
            ):
                content += tok
                yield _sse({"type": "token", "text": tok})

            result = finalize_review(
                content=content, prepared=prepared, provider=provider,
                instructions=body.instructions or "",
            )
            review = Review(
                user_id=caller.user_id,
                topic=body.topic,
                provider=result.provider,
                model=result.model,
                content_md=result.content_md,
                structured=result.structured,
                csl_json=to_csl_json(result.structured.get("sources", [])),
            )
            session.add(review)
            await session.flush()
            await session.commit()
            yield _sse({
                "type": "done",
                "review_id": str(review.id),
                "topic": body.topic,
                "provider": result.provider,
                "model": result.model,
                "structured": result.structured,
            })
        except Exception as exc:  # noqa: BLE001 - report to the client, never 500 the stream
            try:
                await session.rollback()
            except Exception:  # noqa: BLE001
                pass
            yield _sse({"type": "error", "message": str(exc)[:500]})

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@router.post(
    "/multi",
    response_model=MultiReviewOut,
    summary="Generate the same review with several models (parallel, not merged)",
    description="Runs the identical research dataset + instruction through each selected "
    "model concurrently and returns the outputs SEPARATELY so they can be compared and one "
    "chosen. A per-model failure is reported inline without failing the others.",
)
async def multi_review(
    body: MultiReviewCreate, session: SessionDep, caller: RateLimitedKeyDep
) -> MultiReviewOut:
    registry = get_registry()
    providers = list(dict.fromkeys(body.providers))  # de-dupe, preserve order
    unknown = [p for p in providers if p not in registry.keys]
    if unknown:
        raise AppError(
            ErrorCode.UNKNOWN_PROVIDER, f"unknown providers: {unknown}",
            status=400, details=[{"available": registry.keys}],
        )

    payload = body.model_dump(mode="json")
    records = await _gather_records(session, user_id=caller.user_id, payload=payload)
    budget = registry.settings.llm_max_context_tokens
    max_tokens = int(body.max_tokens or 1500)
    instructions = body.instructions or ""

    async def _run(key: str) -> tuple[str, ReviewResult | Exception]:
        try:
            result = await generate_review_content(
                provider=registry.get(key), topic=body.topic, records=records,
                instructions=instructions, token_budget=budget, max_tokens=max_tokens,
            )
            return key, result
        except Exception as exc:  # noqa: BLE001 - captured per-model, others still return
            return key, exc

    # LLM calls run concurrently (no DB); persistence happens sequentially afterwards
    # because a single async DB session must not be written from multiple tasks at once.
    pairs = await asyncio.gather(*(_run(k) for k in providers))

    items: list[MultiReviewItem] = []
    for key, outcome in pairs:
        if isinstance(outcome, Exception):
            items.append(MultiReviewItem(provider=key, error=str(outcome)[:400]))
            continue
        review = Review(
            user_id=caller.user_id, topic=body.topic, provider=outcome.provider,
            model=outcome.model, content_md=outcome.content_md,
            structured=outcome.structured,
            csl_json=to_csl_json(outcome.structured.get("sources", [])),
        )
        session.add(review)
        await session.flush()
        items.append(MultiReviewItem(
            provider=key, model=outcome.model, review_id=review.id,
            content_md=outcome.content_md, structured=outcome.structured,
        ))
    await session.commit()
    return MultiReviewOut(results=items)


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


@router.patch(
    "/{review_id}", response_model=ReviewSummary, summary="Rename a review",
)
async def update_review(
    review_id: uuid.UUID, body: ReviewUpdate, session: SessionDep, caller: RateLimitedKeyDep
) -> ReviewSummary:
    review = await _load_review(session, review_id, caller.user_id)
    review.topic = body.topic
    await session.commit()
    return ReviewSummary(
        id=review.id, topic=review.topic, provider=review.provider, model=review.model,
        created_at=review.created_at,
        sections=len((review.structured or {}).get("sections", []) or []),
    )


@router.delete(
    "/{review_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a review",
)
async def delete_review(
    review_id: uuid.UUID, session: SessionDep, caller: RateLimitedKeyDep
) -> Response:
    review = await _load_review(session, review_id, caller.user_id)
    await session.delete(review)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


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
