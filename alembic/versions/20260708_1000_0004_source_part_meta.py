"""source_part.meta: structure metadata from parsing (headings, RAG_ROADMAP 3.1)

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-08 10:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Nullable, no default: existing rows read as None (no structure info),
    # exactly what pre-0004 parses actually had. Re-parse a source to fill it.
    op.add_column("source_part", sa.Column("meta", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("source_part", "meta")
