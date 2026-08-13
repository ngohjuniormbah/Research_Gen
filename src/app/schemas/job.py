import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from ..models.job import JobStatus


class JobInfo(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    kind: str
    status: JobStatus
    progress: int
    error: str
    result: dict[str, Any]
    created_at: datetime
    updated_at: datetime
