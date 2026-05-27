"""Job status endpoint (M0 surface: read-only)."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from pynote_api.auth import Principal
from pynote_api.deps import current_principal, get_db
from pynote_core.models import Job

router = APIRouter(tags=["jobs"])


class JobOut(BaseModel):
    id: UUID
    kind: str
    status: str
    error: str | None

    model_config = {"from_attributes": True}


@router.get("/jobs/{job_id}", response_model=JobOut)
async def get_job(
    job_id: UUID,
    principal: Principal = Depends(current_principal),
    db: AsyncSession = Depends(get_db),
) -> Job:
    job = await db.get(Job, job_id)
    if job is None or (job.org_id is not None and job.org_id != principal.org_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Job not found.")
    return job
