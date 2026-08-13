"""Document ingestion service: persist the raw upload via the StorageBackend, parse it
into SourceRecords, normalize, and store the parsed metadata on the Document row."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Document
from .ingestion.normalize import normalize_records
from .ingestion.parsers import ParseError, detect_kind, parse_bytes
from .storage import StorageBackend


async def ingest_document(
    session: AsyncSession,
    storage: StorageBackend,
    *,
    user_id: uuid.UUID,
    data: bytes,
    filename: str,
    content_type: str,
) -> Document:
    storage_key = await storage.put(data, filename=filename)
    document = Document(
        user_id=user_id,
        filename=filename,
        content_type=content_type,
        storage_key=storage_key,
        size_bytes=len(data),
        status="parsing",
    )
    try:
        document.kind = detect_kind(filename, content_type)
        records = normalize_records(parse_bytes(data, filename, content_type))
        document.parsed_meta = {
            "record_count": len(records),
            "records": [r.model_dump() for r in records],
        }
        document.status = "parsed"
    except ParseError as exc:
        document.status = "failed"
        document.error = str(exc)[:2000]
        document.parsed_meta = {"record_count": 0, "records": []}

    session.add(document)
    await session.flush()
    return document
