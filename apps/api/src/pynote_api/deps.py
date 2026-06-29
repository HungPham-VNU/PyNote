"""Common FastAPI dependencies."""

from collections.abc import AsyncIterator
from uuid import UUID

from arq.connections import ArqRedis, RedisSettings, create_pool
from fastapi import HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select

from pynote_api.auth import Principal, current_principal
from pynote_core.db import get_async_session
from pynote_core.models import Notebook
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


# ---- Tenant scoping --------------------------------------------------------
#
# A notebook can be either solo (org_id IS NULL, single owner) or org-scoped.
# A principal is either solo (org_id None) or scoped to an active org.
#
#   - Solo principal: may only see notebooks they own that are not in any org.
#   - Org principal:  may see notebooks in their active org plus their own
#     solo notebooks (so switching into an org never hides earlier work).
#
# Every route that loads a notebook by id MUST go through `load_owned_notebook`
# (or scope its query with `scope_notebooks`) — never `db.get(Notebook, id)`
# followed by an org-only check, which both leaks across solo users
# (None != None is False) and hides solo notebooks from org users.


def scope_notebooks(stmt: Select, principal: Principal) -> Select:
    """Restrict a Notebook select to rows the principal can see."""
    if principal.org_id is None:
        return stmt.where(
            Notebook.owner_user_id == principal.user_id,
            Notebook.org_id.is_(None),
        )
    return stmt.where(
        or_(
            Notebook.org_id == principal.org_id,
            Notebook.owner_user_id == principal.user_id,
        )
    )


async def load_owned_notebook(
    notebook_id: UUID,
    principal: Principal,
    db: AsyncSession,
) -> Notebook:
    """Load `notebook_id` if the principal may see it, else raise 404.

    404 (not 403) is intentional — never confirm a notebook exists to someone
    who doesn't have access to it.
    """
    stmt = scope_notebooks(select(Notebook).where(Notebook.id == notebook_id), principal)
    notebook = (await db.execute(stmt)).scalar_one_or_none()
    if notebook is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Notebook not found.")
    return notebook


# Re-export common deps for tidy imports.
__all__ = [
    "Principal",
    "Settings",
    "current_principal",
    "get_arq",
    "get_db",
    "get_settings",
    "load_owned_notebook",
    "scope_notebooks",
]
