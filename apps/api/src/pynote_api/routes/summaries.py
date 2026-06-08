"""Notebook summary endpoints (post-v1 Option A).

POST /api/v1/notebooks/{id}/summary  → generate (regenerates idempotently)
GET  /api/v1/notebooks/{id}/summary  → fetch cached (200 with body or 404)

The summary lives on `notebook.settings["summary"]`. No new table.
"""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pynote_api.auth import Principal
from pynote_api.deps import current_principal, get_db
from pynote_core.models import Notebook, Source, SourcePart
from pynote_core.summarizer import generate_notebook_summary

router = APIRouter(tags=["summaries"])


# ---- response shape -------------------------------------------------------


class NotebookSummaryOut(BaseModel):
    headline: str
    key_points: list[str]
    detailed_summary: str
    generated_at: str
    model_used: str | None = None


# ---- helpers --------------------------------------------------------------


async def _owned_notebook(notebook_id: UUID, principal: Principal, db: AsyncSession) -> Notebook:
    notebook = await db.get(Notebook, notebook_id)
    if notebook is None or notebook.org_id != principal.org_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Notebook not found.")
    return notebook


def _summary_from_settings(settings: dict[str, Any]) -> NotebookSummaryOut | None:
    """Pull the stored summary out of `notebook.settings`, validating shape."""
    raw = settings.get("summary") if isinstance(settings, dict) else None
    if not isinstance(raw, dict):
        return None
    try:
        return NotebookSummaryOut(
            headline=str(raw.get("headline", "")),
            key_points=[str(x) for x in (raw.get("key_points") or [])],
            detailed_summary=str(raw.get("detailed_summary", "")),
            generated_at=str(raw.get("generated_at", "")),
            model_used=raw.get("model_used"),
        )
    except Exception:
        return None


# ---- POST: generate -------------------------------------------------------


@router.post(
    "/notebooks/{notebook_id}/summary",
    response_model=NotebookSummaryOut,
)
async def create_summary(
    notebook_id: UUID,
    principal: Principal = Depends(current_principal),
    db: AsyncSession = Depends(get_db),
) -> NotebookSummaryOut:
    notebook = await _owned_notebook(notebook_id, principal, db)

    # Gather text from every READY source in document order.
    rows = await db.execute(
        select(SourcePart.text)
        .join(Source, Source.id == SourcePart.source_id)
        .where(Source.notebook_id == notebook_id, Source.status == "ready")
        .order_by(Source.created_at, SourcePart.ordinal),
    )
    chunks = [row[0] for row in rows.all() if row[0]]
    if not chunks:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Notebook has no ready sources. Upload and wait for parsing first.",
        )
    joined = "\n\n".join(chunks)

    try:
        summary = await generate_notebook_summary(joined)
    except Exception as e:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            f"Summary generation failed: {type(e).__name__}: {str(e)[:200]}",
        ) from e

    payload: dict[str, Any] = {
        "headline": summary.headline,
        "key_points": list(summary.key_points),
        "detailed_summary": summary.detailed_summary,
        "generated_at": datetime.now(UTC).isoformat(),
        "model_used": type(_unwrap_model_used()).__name__,
    }
    notebook.settings = {**(notebook.settings or {}), "summary": payload}

    return NotebookSummaryOut(**payload)


# ---- GET: fetch cached ----------------------------------------------------


@router.get(
    "/notebooks/{notebook_id}/summary",
    response_model=NotebookSummaryOut,
)
async def get_summary(
    notebook_id: UUID,
    principal: Principal = Depends(current_principal),
    db: AsyncSession = Depends(get_db),
) -> NotebookSummaryOut:
    notebook = await _owned_notebook(notebook_id, principal, db)
    cached = _summary_from_settings(notebook.settings or {})
    if cached is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "No summary generated for this notebook yet.",
        )
    return cached


# ---- internals ------------------------------------------------------------


def _unwrap_model_used() -> Any:
    """Best-effort model class for the response — used only as a label."""
    from pynote_core.llm import get_heavy_model

    try:
        return get_heavy_model()
    except Exception:
        return object()
