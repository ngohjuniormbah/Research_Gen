"""Research sessions — the persistent 'Working Memory'.

Each session stores a JSON snapshot of a full research context (prompt, model, imported
document ids, resolved ORKG records, queries, retrieved data, generated outputs,
references, timestamps) so a Recent Work item reopens the exact state. All operations are
scoped to the calling user — a user can never read or mutate another user's session."""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator

from fastapi import APIRouter, Query, Response, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm.attributes import flag_modified

from ...core.errors import AppError, ErrorCode, not_found
from ...models import ResearchSession
from ...schemas.research_session import (
    ResearchSessionCreate,
    ResearchSessionOut,
    ResearchSessionSummary,
    ResearchSessionUpdate,
    SessionChat,
)
from ...services.llm.registry import get_registry
from ...services.research_chat import build_chat_messages
from ..deps import RateLimitedKeyDep, SessionDep

router = APIRouter(prefix="/api/v1/sessions", tags=["research-sessions"])


def _counts(state: dict) -> tuple[int, int]:
    state = state or {}
    sources = len(state.get("sources", []) or []) + len(state.get("document_ids", []) or [])
    outputs = len(state.get("outputs", []) or [])
    return sources, outputs


def _summary(s: ResearchSession) -> ResearchSessionSummary:
    sources, outputs = _counts(s.state)
    return ResearchSessionSummary(
        id=s.id, title=s.title, starred=s.starred, archived=s.archived,
        created_at=s.created_at, updated_at=s.updated_at, sources=sources, outputs=outputs,
    )


async def _load(
    session: SessionDep, session_id: uuid.UUID, user_id: uuid.UUID
) -> ResearchSession:
    row = await session.get(ResearchSession, session_id)
    if row is None or row.user_id != user_id:
        raise not_found("research session not found")
    return row


@router.post(
    "", response_model=ResearchSessionOut, status_code=status.HTTP_201_CREATED,
    summary="Create a research session",
)
async def create_session(
    body: ResearchSessionCreate, session: SessionDep, caller: RateLimitedKeyDep
) -> ResearchSession:
    row = ResearchSession(user_id=caller.user_id, title=body.title, state=body.state)
    session.add(row)
    await session.commit()
    return row


@router.get(
    "", response_model=list[ResearchSessionSummary],
    summary="List the caller's research sessions (Recent Work)",
)
async def list_sessions(
    session: SessionDep,
    caller: RateLimitedKeyDep,
    q: str | None = Query(None, description="Case-insensitive search over the title."),
    include_archived: bool = Query(False),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> list[ResearchSessionSummary]:
    stmt = select(ResearchSession).where(ResearchSession.user_id == caller.user_id)
    if not include_archived:
        stmt = stmt.where(ResearchSession.archived.is_(False))
    if q and q.strip():
        stmt = stmt.where(ResearchSession.title.ilike(f"%{q.strip()}%"))
    stmt = stmt.order_by(ResearchSession.updated_at.desc()).limit(limit).offset(offset)
    rows = (await session.execute(stmt)).scalars().all()
    return [_summary(r) for r in rows]


@router.get("/{session_id}", response_model=ResearchSessionOut, summary="Open a session")
async def get_session_detail(
    session_id: uuid.UUID, session: SessionDep, caller: RateLimitedKeyDep
) -> ResearchSession:
    return await _load(session, session_id, caller.user_id)


@router.patch(
    "/{session_id}", response_model=ResearchSessionOut,
    summary="Update a session (rename / star / archive / save state)",
)
async def update_session(
    session_id: uuid.UUID,
    body: ResearchSessionUpdate,
    session: SessionDep,
    caller: RateLimitedKeyDep,
) -> ResearchSession:
    row = await _load(session, session_id, caller.user_id)
    if body.title is not None:
        row.title = body.title
    if body.starred is not None:
        row.starred = body.starred
    if body.archived is not None:
        row.archived = body.archived
    if body.state is not None:
        row.state = body.state
    await session.commit()
    return row


@router.post(
    "/{session_id}/chat",
    summary="Ask a follow-up question about the session (grounded, streaming SSE)",
    description="Answers using ONLY the session's Working-Memory context (current "
    "synthesis + sources), streamed as SSE tokens, then persisted to the session's chat "
    "history. The model never invents facts outside the retrieved evidence.",
)
async def chat_session(
    session_id: uuid.UUID,
    body: SessionChat,
    session: SessionDep,
    caller: RateLimitedKeyDep,
) -> StreamingResponse:
    if body.provider and body.provider not in get_registry().keys:
        raise AppError(
            ErrorCode.UNKNOWN_PROVIDER, f"provider '{body.provider}' is not registered",
            status=400, details=[{"available": get_registry().keys}],
        )
    row = await _load(session, session_id, caller.user_id)
    state = dict(row.state or {})
    history: list[dict] = list(state.get("chat") or [])
    provider = get_registry().get(body.provider)
    messages = build_chat_messages(state, history, body.message)

    async def gen() -> AsyncIterator[str]:
        answer = ""
        try:
            async for tok in provider.stream(messages, max_tokens=1200):
                answer += tok
                yield f"data: {json.dumps({'type': 'token', 'text': tok})}\n\n"
            history.append({"role": "user", "text": body.message})
            history.append({"role": "assistant", "text": answer})
            state["chat"] = history
            row.state = state
            flag_modified(row, "state")  # JSON column: ensure the change is persisted
            await session.commit()
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
        except Exception as exc:  # noqa: BLE001 - report to client, never 500 the stream
            try:
                await session.rollback()
            except Exception:  # noqa: BLE001
                pass
            yield f"data: {json.dumps({'type': 'error', 'message': str(exc)[:400]})}\n\n"

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.delete(
    "/{session_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a session",
)
async def delete_session(
    session_id: uuid.UUID, session: SessionDep, caller: RateLimitedKeyDep
) -> Response:
    row = await _load(session, session_id, caller.user_id)
    await session.delete(row)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
