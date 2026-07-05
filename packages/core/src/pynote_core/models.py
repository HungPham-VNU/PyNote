"""SQLModel models for PyNote (M0 surface: tenancy + notebook + job).

Source/chunk/message/artifact models land in M1-M4. Schema is additive —
this file is the canonical declarative source; Alembic migrations are generated from it.
"""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from pgvector.sqlalchemy import Vector
from sqlalchemy import JSON, Column, DateTime, Index, String, Text, func
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlmodel import Field, Relationship, SQLModel

from pynote_core.settings import get_settings


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


def _ts_field(*, on_update: bool = False) -> Any:
    """A timezone-aware timestamp column: Python default + DB `server_default`.

    Centralized so the one SQLModel typing gap we hit — `Field` has no overload
    matching `default_factory` + `sa_type` + `sa_column_kwargs` together — is
    silenced in exactly one place instead of on every timestamp field.
    """
    return Field(  # type: ignore[call-overload]
        default_factory=_utcnow,
        sa_type=DateTime(timezone=True),
        sa_column_kwargs=_ts_kwargs(on_update=on_update),
    )


# ---- Tenancy (Clerk-managed identity) --------------------------------------
#
# We do not own user authentication — Clerk does. We mirror just enough identity
# to scope rows. `org_id` and `user_id` are Clerk's opaque string IDs.


class Org(SQLModel, table=True):
    __tablename__ = "org"

    id: str = Field(primary_key=True, max_length=64)  # Clerk org_id
    name: str = Field(max_length=255)
    settings: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))

    created_at: datetime = _ts_field()
    updated_at: datetime = _ts_field(on_update=True)

    notebooks: list["Notebook"] = Relationship(back_populates="org")


class User(SQLModel, table=True):
    __tablename__ = "user"

    id: str = Field(primary_key=True, max_length=64)  # Clerk user_id
    email: str = Field(max_length=320, index=True)
    display_name: str | None = Field(default=None, max_length=255)

    created_at: datetime = _ts_field()
    updated_at: datetime = _ts_field(on_update=True)


class Membership(SQLModel, table=True):
    __tablename__ = "membership"

    user_id: str = Field(primary_key=True, foreign_key="user.id", max_length=64)
    org_id: str = Field(primary_key=True, foreign_key="org.id", max_length=64)
    role: str = Field(default="member", max_length=32)  # member | admin | owner

    created_at: datetime = _ts_field()
    updated_at: datetime = _ts_field(on_update=True)


# ---- Notebook --------------------------------------------------------------


class Notebook(SQLModel, table=True):
    __tablename__ = "notebook"
    __table_args__ = (
        Index("ix_notebook_org_created", "org_id", "created_at"),
        Index("ix_notebook_owner_created", "owner_user_id", "created_at"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    org_id: str | None = Field(default=None, foreign_key="org.id", max_length=64, index=True)
    owner_user_id: str = Field(foreign_key="user.id", max_length=64, index=True)
    title: str = Field(max_length=255)
    settings: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))

    created_at: datetime = _ts_field()
    updated_at: datetime = _ts_field(on_update=True)

    org: Org | None = Relationship(back_populates="notebooks")
    sources: list["Source"] = Relationship(back_populates="notebook")


# ---- Source + parts (M1) ---------------------------------------------------
#
# A Source is one uploaded/linked item inside a notebook (PDF in M1; DOCX/URL/
# YouTube/audio/image/note land in M8/M9). SourceParts are the loader's raw
# units — for PDFs, one row per page.


class Source(SQLModel, table=True):
    __tablename__ = "source"
    __table_args__ = (Index("ix_source_notebook_created", "notebook_id", "created_at"),)

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    notebook_id: UUID = Field(foreign_key="notebook.id", index=True)
    kind: str = Field(max_length=16)  # pdf | docx | url | youtube | audio | image | note
    status: str = Field(default="pending", sa_column=Column(String(16), index=True))
    # pending → uploading → parsing → parsed → embedding → ready  (failed on error)
    title: str = Field(max_length=512)
    bytes_uri: str | None = Field(default=None, max_length=1024)  # s3://bucket/key
    byte_size: int | None = Field(default=None)
    content_hash: str | None = Field(default=None, max_length=64, index=True)  # sha256 hex
    error: str | None = Field(default=None)
    meta: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))

    created_at: datetime = _ts_field()
    updated_at: datetime = _ts_field(on_update=True)

    notebook: Notebook = Relationship(back_populates="sources")
    parts: list["SourcePart"] = Relationship(
        back_populates="source",
        sa_relationship_kwargs={"cascade": "all, delete-orphan", "order_by": "SourcePart.ordinal"},
    )


class SourcePart(SQLModel, table=True):
    __tablename__ = "source_part"
    __table_args__ = (Index("ix_source_part_source_ordinal", "source_id", "ordinal", unique=True),)

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    source_id: UUID = Field(foreign_key="source.id", index=True)
    ordinal: int = Field()  # 0-based position within the source
    page: int | None = Field(default=None)  # 1-based page number for PDFs
    text: str = Field()  # extracted text; "" allowed for image-only pages
    bbox: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))

    created_at: datetime = _ts_field()

    source: Source = Relationship(back_populates="parts")
    chunks: list["Chunk"] = Relationship(
        back_populates="part",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )


# ---- Chunk (M2) ------------------------------------------------------------
#
# Retrieval unit. One PDF page (= SourcePart) yields multiple Chunks via the
# char-based hierarchical chunker. Schema supports both fine (level 0) and
# section (level 1) chunks — M2 writes only level 0 (M2's chunker is flat;
# section detection lands when we adopt Docling).
#
# `(notebook_id, source_id, source_part_id)` is denormalized so the search
# query can filter on notebook_id without joins.


class Chunk(SQLModel, table=True):
    __tablename__ = "chunk"
    __table_args__ = (
        Index("ix_chunk_notebook_id", "notebook_id"),
        Index("ix_chunk_source_level", "source_id", "level"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    notebook_id: UUID = Field(foreign_key="notebook.id")
    source_id: UUID = Field(foreign_key="source.id")
    source_part_id: UUID = Field(foreign_key="source_part.id")
    parent_chunk_id: UUID | None = Field(default=None, foreign_key="chunk.id")
    level: int = Field(default=0)  # 0 = fine, 1 = section, 2 = doc summary
    ordinal: int = Field()  # position within the source (across all parts)
    text: str = Field(sa_column=Column(Text, nullable=False))
    char_start: int = Field()  # offsets into source_part.text — citation contract
    char_end: int = Field()
    embedding: list[float] | None = Field(
        default=None,
        sa_column=Column(Vector(get_settings().embedding_dim), nullable=True),
    )
    # tsv is populated by SQL (to_tsvector); the Python column is a passthrough.
    tsv: str | None = Field(default=None, sa_column=Column(TSVECTOR, nullable=True))
    meta: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))

    created_at: datetime = _ts_field()

    part: SourcePart = Relationship(back_populates="chunks")


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

    created_at: datetime = _ts_field()
    updated_at: datetime = _ts_field(on_update=True)
