"""SQLModel models for PyNote (M0 surface: tenancy + notebook + job).

Source/chunk/message/artifact models land in M1-M4. Schema is additive —
this file is the canonical declarative source; Alembic migrations are generated from it.
"""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import JSON, Column, DateTime, Index, String, func
from sqlmodel import Field, Relationship, SQLModel


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _ts_kwargs(*, on_update: bool = False) -> dict[str, Any]:
    """Per-call kwargs dict so SQLModel constructs a fresh Column for each field.

    Sharing a Column() instance across models (via a Mixin) trips SQLAlchemy's
    `Column already assigned to Table` check — this avoids it.
    """
    kw: dict[str, Any] = {"server_default": func.now(), "nullable": False}
    if on_update:
        kw["onupdate"] = func.now()
    return kw


# ---- Tenancy (Clerk-managed identity) --------------------------------------
#
# We do not own user authentication — Clerk does. We mirror just enough identity
# to scope rows. `org_id` and `user_id` are Clerk's opaque string IDs.


class Org(SQLModel, table=True):
    __tablename__ = "org"

    id: str = Field(primary_key=True, max_length=64)  # Clerk org_id
    name: str = Field(max_length=255)
    settings: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))

    created_at: datetime = Field(
        default_factory=_utcnow,
        sa_type=DateTime(timezone=True),
        sa_column_kwargs=_ts_kwargs(),
    )
    updated_at: datetime = Field(
        default_factory=_utcnow,
        sa_type=DateTime(timezone=True),
        sa_column_kwargs=_ts_kwargs(on_update=True),
    )

    notebooks: list["Notebook"] = Relationship(back_populates="org")


class User(SQLModel, table=True):
    __tablename__ = "user"

    id: str = Field(primary_key=True, max_length=64)  # Clerk user_id
    email: str = Field(max_length=320, index=True)
    display_name: str | None = Field(default=None, max_length=255)

    created_at: datetime = Field(
        default_factory=_utcnow,
        sa_type=DateTime(timezone=True),
        sa_column_kwargs=_ts_kwargs(),
    )
    updated_at: datetime = Field(
        default_factory=_utcnow,
        sa_type=DateTime(timezone=True),
        sa_column_kwargs=_ts_kwargs(on_update=True),
    )


class Membership(SQLModel, table=True):
    __tablename__ = "membership"

    user_id: str = Field(primary_key=True, foreign_key="user.id", max_length=64)
    org_id: str = Field(primary_key=True, foreign_key="org.id", max_length=64)
    role: str = Field(default="member", max_length=32)  # member | admin | owner

    created_at: datetime = Field(
        default_factory=_utcnow,
        sa_type=DateTime(timezone=True),
        sa_column_kwargs=_ts_kwargs(),
    )
    updated_at: datetime = Field(
        default_factory=_utcnow,
        sa_type=DateTime(timezone=True),
        sa_column_kwargs=_ts_kwargs(on_update=True),
    )


# ---- Notebook --------------------------------------------------------------


class Notebook(SQLModel, table=True):
    __tablename__ = "notebook"
    __table_args__ = (
        Index("ix_notebook_org_created", "org_id", "created_at"),
        Index("ix_notebook_owner_created", "owner_user_id", "created_at"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    org_id: str | None = Field(
        default=None, foreign_key="org.id", max_length=64, index=True
    )
    owner_user_id: str = Field(foreign_key="user.id", max_length=64, index=True)
    title: str = Field(max_length=255)
    settings: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))

    created_at: datetime = Field(
        default_factory=_utcnow,
        sa_type=DateTime(timezone=True),
        sa_column_kwargs=_ts_kwargs(),
    )
    updated_at: datetime = Field(
        default_factory=_utcnow,
        sa_type=DateTime(timezone=True),
        sa_column_kwargs=_ts_kwargs(on_update=True),
    )

    org: Org | None = Relationship(back_populates="notebooks")


# ---- Job (arq task envelope) -----------------------------------------------


class Job(SQLModel, table=True):
    __tablename__ = "job"
    __table_args__ = (Index("ix_job_org_status", "org_id", "status"),)

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    org_id: str | None = Field(default=None, foreign_key="org.id", max_length=64, index=True)
    kind: str = Field(
        max_length=64, index=True
    )  # parse_source | embed_source | outline_source | ...
    status: str = Field(default="pending", sa_column=Column(String(16), index=True))
    payload: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    error: str | None = Field(default=None)
    arq_job_id: str | None = Field(default=None, max_length=64, index=True)

    created_at: datetime = Field(
        default_factory=_utcnow,
        sa_type=DateTime(timezone=True),
        sa_column_kwargs=_ts_kwargs(),
    )
    updated_at: datetime = Field(
        default_factory=_utcnow,
        sa_type=DateTime(timezone=True),
        sa_column_kwargs=_ts_kwargs(on_update=True),
    )
