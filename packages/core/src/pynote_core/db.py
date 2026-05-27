"""Async SQLAlchemy engine + session helpers.

Use `get_async_session()` as a FastAPI dependency, or `async_session_scope()`
as a context manager outside of request scope (e.g. arq workers).
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from functools import lru_cache

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from pynote_core.settings import get_settings


def _async_url(url: str) -> str:
    """Normalize a DSN for SQLAlchemy + psycopg3 async.

    psycopg3 uses the same dialect (`postgresql+psycopg`) for sync and async;
    async-ness is selected by `create_async_engine` vs `create_engine`.
    Bare `postgresql://` is rewritten so SQLAlchemy uses psycopg3 (not psycopg2).
    """
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


@lru_cache(maxsize=1)
def get_engine() -> AsyncEngine:
    settings = get_settings()
    return create_async_engine(
        _async_url(settings.database_url),
        echo=False,
        pool_pre_ping=True,
        pool_size=10,
        max_overflow=10,
    )


@lru_cache(maxsize=1)
def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(get_engine(), expire_on_commit=False)


async def get_async_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency. Yields an AsyncSession; commits on success, rolls back on error."""
    sm = get_sessionmaker()
    async with sm() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


@asynccontextmanager
async def async_session_scope() -> AsyncIterator[AsyncSession]:
    """Out-of-request scope — for workers and scripts."""
    sm = get_sessionmaker()
    async with sm() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
