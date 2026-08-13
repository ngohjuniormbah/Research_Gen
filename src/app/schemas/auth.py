import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class ApiKeyCreate(BaseModel):
    email: EmailStr
    name: str = Field(default="", max_length=200)


class ApiKeyInfo(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    prefix: str
    revoked_at: datetime | None
    last_used_at: datetime | None
    created_at: datetime


class ApiKeyCreated(ApiKeyInfo):
    # Plaintext key, returned exactly once at creation time.
    api_key: str
