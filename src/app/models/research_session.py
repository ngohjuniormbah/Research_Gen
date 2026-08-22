import uuid
from typing import Any

from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from ..db.base import Base, TimestampMixin
from ..db.types import JSONBType


class ResearchSession(TimestampMixin, Base):
    """A persistent research session — the "Working Memory".

    ``state`` is a free-form JSON snapshot of everything needed to reopen the session:
    prompt, selected model, imported document ids, resolved ORKG records, ORKG query,
    retrieved data, generated outputs, references, etc. Keeping it as one JSON document
    lets the working-memory schema evolve without a migration per field.
    """

    __tablename__ = "research_sessions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(1000), default="")
    starred: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    archived: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    state: Mapped[dict[str, Any]] = mapped_column(JSONBType, default=dict)
