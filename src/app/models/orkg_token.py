from sqlalchemy import Float, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..db.base import Base, TimestampMixin


class OrkgToken(TimestampMixin, Base):
    """Durable per-user ORKG OIDC token, encrypted at rest.

    Persisting the token in the database (instead of process memory) keeps a user's ORKG
    connection alive across page refreshes, new browser sessions, and backend
    redeploys/instance recycles. ``user_key`` is the caller's stable API-key user id.
    """

    __tablename__ = "orkg_tokens"

    user_key: Mapped[str] = mapped_column(String(255), primary_key=True)
    access_token_enc: Mapped[str] = mapped_column(Text, default="", nullable=False)
    refresh_token_enc: Mapped[str] = mapped_column(Text, default="", nullable=False)
    expires_at: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
