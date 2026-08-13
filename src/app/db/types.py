from sqlalchemy import JSON
from sqlalchemy.dialects.postgresql import JSONB

# JSONB on Postgres (prod), plain JSON on SQLite (tests). One type, both dialects.
JSONBType = JSON().with_variant(JSONB(), "postgresql")
