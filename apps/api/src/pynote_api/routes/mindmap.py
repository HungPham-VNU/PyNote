"""Notebook mind-map endpoints (M12).

POST /api/v1/notebooks/{id}/mind-map  → enqueue generation (idempotent kick-off)
GET  /api/v1/notebooks/{id}/mind-map  → fetch cached map / status

The map lives on `notebook.settings["mind_map"]`, same pattern as the
post-v1 summary artifact (`pynote_api.routes.summaries`). No new table.
Generation is async (arq job) rather than inline like the summary route,
because a 20-source notebook's two-pass extraction can run well past a
typical request timeout.
"""

from typing import Any, Literal
from uuid import UUID

from arq.connections import ArqRedis
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from pynote_api.auth import Principal
from pynote_api.deps import current_principal, get_arq, get_db, load_owned_notebook

router = APIRouter(tags=["mindmap"])


# ---- response shapes -------------------------------------------------------


class MindMapCitationOut(BaseModel):
    source_id: UUID
    source_part_id: UUID
    source_title: str | None
    page: int | None
    quote: str
    roundtrip_ok: bool


class MindMapNodeOut(BaseModel):
    id: str
    label: str
    kind: str
    citations: list[MindMapCitationOut]


class MindMapEdgeOut(BaseModel):
    from_: str = Field(alias="from")
    to: str
    label: str
    citations: list[MindMapCitationOut]

    model_config = {"populate_by_name": True}


class MindMapOut(BaseModel):
    status: Literal["generating", "ready", "failed"]
    generated_at: str | None = None
    error: str | None = None
    nodes: list[MindMapNodeOut] = []
    edges: list[MindMapEdgeOut] = []


# ---- helpers ----------------------------------------------------------------


def _mind_map_from_settings(settings: dict[str, Any]) -> MindMapOut | None:
    """Pull the stored mind map out of `notebook.settings`, validating shape.

    Stored JSON already uses by-alias keys (`from`/`to` on edges), matching
    what `MindMapOut` expects on the wire — `model_validate` does the coercion.
    """
    raw = settings.get("mind_map") if isinstance(settings, dict) else None
    if not isinstance(raw, dict):
        return None
    try:
        return MindMapOut.model_validate(raw)
    except Exception:
        return None


# ---- POST: kick off generation ---------------------------------------------


@router.post(
    "/notebooks/{notebook_id}/mind-map",
    response_model=MindMapOut,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_mind_map(
    notebook_id: UUID,
    principal: Principal = Depends(current_principal),
    db: AsyncSession = Depends(get_db),
    arq: ArqRedis = Depends(get_arq),
) -> MindMapOut:
    notebook = await load_owned_notebook(notebook_id, principal, db)
    notebook.settings = {**(notebook.settings or {}), "mind_map": {"status": "generating"}}
    await db.flush()

    await arq.enqueue_job("generate_mind_map_task", str(notebook_id))
    return MindMapOut(status="generating")


# ---- GET: fetch cached / status ---------------------------------------------


@router.get(
    "/notebooks/{notebook_id}/mind-map",
    response_model=MindMapOut,
)
async def get_mind_map(
    notebook_id: UUID,
    principal: Principal = Depends(current_principal),
    db: AsyncSession = Depends(get_db),
) -> MindMapOut:
    notebook = await load_owned_notebook(notebook_id, principal, db)
    cached = _mind_map_from_settings(notebook.settings or {})
    if cached is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "No mind map generated for this notebook yet.",
        )
    return cached
