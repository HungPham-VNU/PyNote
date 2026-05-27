"""Liveness + readiness probes."""

from fastapi import APIRouter, Depends, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from pynote_api.deps import get_db

router = APIRouter(tags=["health"])


@router.get("/healthz", status_code=status.HTTP_200_OK)
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/readyz")
async def readyz(db: AsyncSession = Depends(get_db)) -> dict[str, object]:
    """Verifies DB reachable + extensions present."""
    row = await db.execute(
        text("SELECT extname FROM pg_extension WHERE extname IN ('vector', 'pg_trgm')")
    )
    extensions = sorted({r[0] for r in row.all()})
    return {"status": "ok", "db": "ok", "extensions": extensions}
