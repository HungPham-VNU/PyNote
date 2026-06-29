"""Notebook CRUD (M0 surface)."""

from uuid import UUID

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pynote_api.auth import Principal
from pynote_api.deps import current_principal, get_db, load_owned_notebook, scope_notebooks
from pynote_core.models import Membership, Notebook, Org, User

router = APIRouter(tags=["notebooks"])


class NotebookCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)


class NotebookOut(BaseModel):
    id: UUID
    title: str
    org_id: str | None
    owner_user_id: str

    model_config = {"from_attributes": True}


async def _ensure_identity(db: AsyncSession, principal: Principal) -> None:
    """Upsert minimal User (and Org/Membership when scoped) rows for FKs.

    Clerk owns identity; we just mirror enough to scope tenant rows.
    """
    user = await db.get(User, principal.user_id)
    if user is None:
        db.add(User(id=principal.user_id, email=principal.email or f"{principal.user_id}@unknown"))
    if principal.org_id is not None:
        org = await db.get(Org, principal.org_id)
        if org is None:
            db.add(Org(id=principal.org_id, name=principal.org_id))
    await db.flush()
    if principal.org_id is not None:
        membership = await db.get(Membership, (principal.user_id, principal.org_id))
        if membership is None:
            db.add(Membership(user_id=principal.user_id, org_id=principal.org_id, role="member"))
            await db.flush()


@router.get("/notebooks", response_model=list[NotebookOut])
async def list_notebooks(
    principal: Principal = Depends(current_principal),
    db: AsyncSession = Depends(get_db),
) -> list[Notebook]:
    stmt = scope_notebooks(select(Notebook), principal).order_by(Notebook.created_at.desc())
    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.post(
    "/notebooks",
    response_model=NotebookOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_notebook(
    payload: NotebookCreate,
    principal: Principal = Depends(current_principal),
    db: AsyncSession = Depends(get_db),
) -> Notebook:
    await _ensure_identity(db, principal)
    notebook = Notebook(
        org_id=principal.org_id,
        owner_user_id=principal.user_id,
        title=payload.title,
    )
    db.add(notebook)
    await db.flush()
    return notebook


@router.get("/notebooks/{notebook_id}", response_model=NotebookOut)
async def get_notebook(
    notebook_id: UUID,
    principal: Principal = Depends(current_principal),
    db: AsyncSession = Depends(get_db),
) -> Notebook:
    return await load_owned_notebook(notebook_id, principal, db)


@router.delete("/notebooks/{notebook_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_notebook(
    notebook_id: UUID,
    principal: Principal = Depends(current_principal),
    db: AsyncSession = Depends(get_db),
) -> None:
    notebook = await load_owned_notebook(notebook_id, principal, db)
    await db.delete(notebook)
