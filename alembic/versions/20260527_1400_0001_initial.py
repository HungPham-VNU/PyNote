"""initial: extensions + tenancy + notebook + job

Revision ID: 0001
Revises:
Create Date: 2026-05-27 14:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Extensions (idempotent — docker-init also creates them, but Alembic owns the schema).
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gin")

    op.create_table(
        "org",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("settings", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "user",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_user_email", "user", ["email"])

    op.create_table(
        "membership",
        sa.Column("user_id", sa.String(length=64), sa.ForeignKey("user.id"), primary_key=True),
        sa.Column("org_id", sa.String(length=64), sa.ForeignKey("org.id"), primary_key=True),
        sa.Column("role", sa.String(length=32), nullable=False, server_default="member"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "notebook",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("org_id", sa.String(length=64), sa.ForeignKey("org.id"), nullable=False),
        sa.Column("owner_user_id", sa.String(length=64), sa.ForeignKey("user.id"), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("settings", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_notebook_org_id", "notebook", ["org_id"])
    op.create_index("ix_notebook_owner_user_id", "notebook", ["owner_user_id"])
    op.create_index("ix_notebook_org_created", "notebook", ["org_id", "created_at"])

    op.create_table(
        "job",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("org_id", sa.String(length=64), sa.ForeignKey("org.id"), nullable=True),
        sa.Column("kind", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("payload", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("arq_job_id", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_job_kind", "job", ["kind"])
    op.create_index("ix_job_status", "job", ["status"])
    op.create_index("ix_job_org_id", "job", ["org_id"])
    op.create_index("ix_job_org_status", "job", ["org_id", "status"])
    op.create_index("ix_job_arq_job_id", "job", ["arq_job_id"])


def downgrade() -> None:
    op.drop_table("job")
    op.drop_table("notebook")
    op.drop_table("membership")
    op.drop_table("user")
    op.drop_table("org")
    # Leave extensions in place — they may be used by other databases.
