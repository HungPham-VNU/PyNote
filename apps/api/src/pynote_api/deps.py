"""Common FastAPI dependencies."""

from collections.abc import AsyncIterator

from arq.connections import ArqRedis, RedisSettings, create_pool
from sqlalchemy.ext.asyncio import AsyncSession

from pynote_api.auth import Principal, current_principal
from pynote_core.db import get_async_session
from pynote_core.settings import Settings, get_settings


async def get_db() -> AsyncIterator[AsyncSession]:
    async for session in get_async_session():
        yield session


async def get_arq() -> AsyncIterator[ArqRedis]:
    settings = get_settings()
    pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    try:
        yield pool
    finally:
        await pool.close()


# Re-export common deps for tidy imports.
__all__ = [
    "Principal",
    "Settings",
    "current_principal",
    "get_arq",
    "get_db",
    "get_settings",
]
