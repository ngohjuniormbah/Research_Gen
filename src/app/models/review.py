import uuid
from typing import Any

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..db.base import Base, TimestampMixin
from ..db.types import JSONBType


class Review(TimestampMixin, Base):
    __tablename__ = "reviews"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("jobs.id", ondelete="SET NULL"), default=None, index=True
    )
    topic: Mapped[str] = mapped_column(String(1000), default="")
    provider: Mapped[str] = mapped_column(String(50), default="")
    model: Mapped[str] = mapped_column(String(100), default="")
    content_md: Mapped[str] = mapped_column(Text, default="")
    # Structured breakdown: {"sections": [...], "citations": [...], "sources": [...]}
    structured: Mapped[dict[str, Any]] = mapped_column(JSONBType, default=dict)
