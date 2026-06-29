"""Liveness + readiness probes.

`/healthz` is a liveness check: always cheap, no I/O. Use for k8s liveness.
`/readyz` is per-component: each dependency reports `ok` / `degraded` / `down`
with a `latency_ms` and optional `detail`. Use for k8s readiness, dashboards,
and the M3 prototype's smoke test.
"""

import asyncio
import time
from typing import Literal

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from pynote_api.deps import get_db

router = APIRouter(tags=["health"])

ComponentStatus = Literal["ok", "degraded", "down"]


class ComponentReport(BaseModel):
    status: ComponentStatus
    latency_ms: int | None = None
    detail: str | None = None


class ReadyReport(BaseModel):
    status: ComponentStatus
    components: dict[str, ComponentReport]


@router.get("/healthz", status_code=status.HTTP_200_OK)
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


async def _check_postgres(db: AsyncSession) -> ComponentReport:
    started = time.perf_counter()
    try:
        row = await asyncio.wait_for(
            db.execute(
                text(
                    "SELECT extname FROM pg_extension "
                    "WHERE extname IN ('vector', 'pg_trgm', 'btree_gin')"
                )
            ),
            timeout=2.0,
        )
        exts = sorted({r[0] for r in row.all()})
        missing = {"vector", "pg_trgm"} - set(exts)
        return ComponentReport(
            status="degraded" if missing else "ok",
            latency_ms=int((time.perf_counter() - started) * 1000),
            detail=f"extensions={exts}" + (f"; missing={sorted(missing)}" if missing else ""),
        )
    except (TimeoutError, Exception) as e:
        return ComponentReport(
            status="down",
            latency_ms=int((time.perf_counter() - started) * 1000),
            detail=str(e)[:200],
        )


# Stubs for providers added in M1/M2/M3 — implement when those layers land.
# Returning "ok" with detail="not checked" keeps the contract stable.
async def _check_redis() -> ComponentReport:
    return ComponentReport(status="ok", detail="not checked (M0)")


async def _check_object_store() -> ComponentReport:
    return ComponentReport(status="ok", detail="not checked (added in M1)")


async def _check_llm() -> ComponentReport:
    return ComponentReport(status="ok", detail="not checked (added in M3)")


def _overall(components: dict[str, ComponentReport]) -> ComponentStatus:
    statuses = {c.status for c in components.values()}
    if "down" in statuses:
        return "down"
    if "degraded" in statuses:
        return "degraded"
    return "ok"


@router.get("/readyz", response_model=ReadyReport)
async def readyz(db: AsyncSession = Depends(get_db)) -> ReadyReport:
    """Reports each dependency individually. Always 200 — read the body."""
    components = {
        "postgres": await _check_postgres(db),
        "redis": await _check_redis(),
        "object_store": await _check_object_store(),
        "llm": await _check_llm(),
    }
    return ReadyReport(status=_overall(components), components=components)
