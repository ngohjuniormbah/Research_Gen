import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class DocumentInfo(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    filename: str
    content_type: str
    kind: str
    size_bytes: int
    status: str
    error: str
    parsed_meta: dict[str, Any]
    created_at: datetime
