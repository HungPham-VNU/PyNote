"""chunks: chunk table + HNSW (dense) + GIN (sparse) indexes (M2)

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-31 19:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects.postgresql import TSVECTOR

from pynote_core.settings import get_settings

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    dim = get_settings().embedding_dim

    op.create_table(
        "chunk",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("notebook_id", sa.Uuid(), sa.ForeignKey("notebook.id"), nullable=False),
        sa.Column("source_id", sa.Uuid(), sa.ForeignKey("source.id"), nullable=False),
        sa.Column("source_part_id", sa.Uuid(), sa.ForeignKey("source_part.id"), nullable=False),
        sa.Column("parent_chunk_id", sa.Uuid(), sa.ForeignKey("chunk.id"), nullable=True),
        sa.Column("level", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("char_start", sa.Integer(), nullable=False),
        sa.Column("char_end", sa.Integer(), nullable=False),
        sa.Column("embedding", Vector(dim), nullable=True),
        sa.Column("tsv", TSVECTOR(), nullable=True),
        sa.Column("meta", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    op.create_index("ix_chunk_notebook_id", "chunk", ["notebook_id"])
    op.create_index("ix_chunk_source_level", "chunk", ["source_id", "level"])

    # Dense vector index — cosine distance (matches normalized BGE/Voyage embeddings).
    # ef_construction/m are HNSW defaults that work well up to ~1M chunks.
    op.execute(
        "CREATE INDEX ix_chunk_embedding_hnsw ON chunk "
        "USING hnsw (embedding vector_cosine_ops) WITH (m=16, ef_construction=64)"
    )
    # Sparse: GIN on tsvector for full-text search.
    op.execute("CREATE INDEX ix_chunk_tsv_gin ON chunk USING gin (tsv)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_chunk_tsv_gin")
    op.execute("DROP INDEX IF EXISTS ix_chunk_embedding_hnsw")
    op.drop_table("chunk")
