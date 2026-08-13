import uuid
from typing import Any

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from ..db.base import Base, TimestampMixin
from ..db.types import JSONBType


class Document(TimestampMixin, Base):
    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    filename: Mapped[str] = mapped_column(String(500), default="")
    content_type: Mapped[str] = mapped_column(String(200), default="")
    # Parser family used: csv | xlsx | pdf | json
    kind: Mapped[str] = mapped_column(String(20), default="")
    # Where the raw upload lives in the StorageBackend.
    storage_key: Mapped[str] = mapped_column(String(1000), default="")
    size_bytes: Mapped[int] = mapped_column(default=0)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    error: Mapped[str] = mapped_column(String(2000), default="")
    # Parsed metadata: record_count plus the normalized list[SourceRecord].
    parsed_meta: Mapped[dict[str, Any]] = mapped_column(JSONBType, default=dict)
