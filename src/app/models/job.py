import enum
import uuid
from typing import Any

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from ..db.base import Base, TimestampMixin
from ..db.types import JSONBType


class JobStatus(enum.StrEnum):
    queued = "queued"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"


class Job(TimestampMixin, Base):
    """First-class job record driving every async operation (generation, etc.)."""

    __tablename__ = "jobs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(50), default="generate_review")
    status: Mapped[JobStatus] = mapped_column(
        String(20), default=JobStatus.queued, index=True
    )
    progress: Mapped[int] = mapped_column(default=0)
    input: Mapped[dict[str, Any]] = mapped_column(JSONBType, default=dict)
    result: Mapped[dict[str, Any]] = mapped_column(JSONBType, default=dict)
    error: Mapped[str] = mapped_column(String(2000), default="")
