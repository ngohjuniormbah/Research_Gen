from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, File, UploadFile, status

from ...core.errors import AppError
from ...models import Document
from ...schemas.document import DocumentInfo
from ...services.documents import ingest_document
from ..deps import ApiKeyDep, SessionDep, StorageDep

router = APIRouter(prefix="/api/v1/documents", tags=["documents"])


@router.post("", response_model=DocumentInfo, status_code=status.HTTP_201_CREATED)
async def upload_document(
    session: SessionDep,
    storage: StorageDep,
    caller: ApiKeyDep,
    file: Annotated[UploadFile, File(...)],
) -> Document:
    """Upload a CSV/XLSX/PDF/JSON file. It is stored, parsed into SourceRecords, and
    normalized. A parse failure still returns a Document with status='failed'."""
    data = await file.read()
    if not data:
        raise AppError("empty_file", "uploaded file is empty", status=400)
    document = await ingest_document(
        session,
        storage,
        user_id=caller.user_id,
        data=data,
        filename=file.filename or "upload",
        content_type=file.content_type or "",
    )
    await session.commit()
    return document


@router.get("/{document_id}", response_model=DocumentInfo)
async def get_document(document_id: uuid.UUID, session: SessionDep, caller: ApiKeyDep) -> Document:
    document = await session.get(Document, document_id)
    if document is None or document.user_id != caller.user_id:
        raise AppError("not_found", "document not found", status=404)
    return document
