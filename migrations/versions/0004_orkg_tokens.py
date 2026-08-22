"""orkg_tokens (durable ORKG OIDC token, encrypted at rest)

Revision ID: 0004_orkg_tokens
Revises: 0003_research_sessions
Create Date: 2026-08-22
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_orkg_tokens"
down_revision: str | None = "0003_research_sessions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_NOW = sa.text("now()")


def upgrade() -> None:
    op.create_table(
        "orkg_tokens",
        sa.Column("user_key", sa.String(255), primary_key=True),
        sa.Column("access_token_enc", sa.Text(), nullable=False, server_default=""),
        sa.Column("refresh_token_enc", sa.Text(), nullable=False, server_default=""),
        sa.Column("expires_at", sa.Float(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
    )


def downgrade() -> None:
    op.drop_table("orkg_tokens")
