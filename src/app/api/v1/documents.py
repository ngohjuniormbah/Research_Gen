from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, File, UploadFile, status

from ...core.errors import AppError, ErrorCode, not_found
from ...models import Document
from ...schemas.document import DocumentInfo
from ...services.documents import ingest_document
from ..deps import RateLimitedKeyDep, SessionDep, SettingsDep, StorageDep

router = APIRouter(prefix="/api/v1/documents", tags=["documents"])


@router.post(
    "",
    response_model=DocumentInfo,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a source file",
    description="Upload a **CSV / XLSX / PDF / JSON** file. It is stored, its type is "
    "verified by magic bytes, then it is parsed into normalized SourceRecords. A parse "
    "failure still returns a Document with `status='failed'` and an `error`.",
)
async def upload_document(
    session: SessionDep,
    settings: SettingsDep,
    storage: StorageDep,
    caller: RateLimitedKeyDep,
    file: Annotated[UploadFile, File(...)],
) -> Document:
    data = await file.read()
    if not data:
        raise AppError(ErrorCode.VALIDATION, "uploaded file is empty", status=422,
                       details=[{"field": "file", "message": "file is empty"}])
    if len(data) > settings.max_upload_bytes:
        raise AppError(
            ErrorCode.PAYLOAD_TOO_LARGE,
            f"file exceeds the {settings.max_upload_bytes} byte limit",
            status=413,
            details=[{"field": "file", "size": len(data), "limit": settings.max_upload_bytes}],
        )
    document = await ingest_document(
        session,
        storage,
        user_id=caller.user_id,
        data=data,
        filename=file.filename or "upload",
        content_type=file.content_type or "",
        max_records=settings.max_source_records,
    )
    await session.commit()
    return document


@router.get(
    "/{document_id}",
    response_model=DocumentInfo,
    summary="Get a document's parse status + metadata",
)
async def get_document(
    document_id: uuid.UUID, session: SessionDep, caller: RateLimitedKeyDep
) -> Document:
    document = await session.get(Document, document_id)
    if document is None or document.user_id != caller.user_id:
        raise not_found("document not found")
    return document
