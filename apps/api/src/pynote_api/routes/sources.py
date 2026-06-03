"""Source endpoints (M1: PDF upload + list + get + delete).

Upload flow (multipart):
    POST /notebooks/{nb_id}/sources/upload
      -> S3 put, Source row, enqueue parse_source
We use multipart-through-API instead of presigned-direct-to-S3 because it's
simpler and 30MB PDFs upload fine through it. Presign lands later (see PLAN.md).
"""

from collections.abc import Iterable
from contextlib import suppress
from uuid import UUID, uuid4

from arq.connections import ArqRedis
from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pynote_api.auth import Principal
from pynote_api.deps import current_principal, get_arq, get_db
from pynote_core.models import Notebook, Source, SourcePart
from pynote_core.storage import delete as s3_delete
from pynote_core.storage import get_object_stream, upload_bytes

MAX_UPLOAD_BYTES = 30 * 1024 * 1024  # 30 MB — bump when we add presign
PDF_CONTENT_TYPE = "application/pdf"

router = APIRouter(tags=["sources"])


class SourceOut(BaseModel):
    id: UUID
    notebook_id: UUID
    kind: str
    status: str
    title: str
    byte_size: int | None
    error: str | None

    model_config = {"from_attributes": True}


class SourcePartOut(BaseModel):
    ordinal: int
    page: int | None
    text: str

    model_config = {"from_attributes": True}


async def _owned_notebook(notebook_id: UUID, principal: Principal, db: AsyncSession) -> Notebook:
    notebook = await db.get(Notebook, notebook_id)
    if notebook is None or notebook.org_id != principal.org_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Notebook not found.")
    return notebook


async def _owned_source(source_id: UUID, principal: Principal, db: AsyncSession) -> Source:
    source = await db.get(Source, source_id)
    if source is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Source not found.")
    await _owned_notebook(source.notebook_id, principal, db)
    return source


@router.get("/notebooks/{notebook_id}/sources", response_model=list[SourceOut])
async def list_sources(
    notebook_id: UUID,
    principal: Principal = Depends(current_principal),
    db: AsyncSession = Depends(get_db),
) -> list[Source]:
    await _owned_notebook(notebook_id, principal, db)
    result = await db.execute(
        select(Source).where(Source.notebook_id == notebook_id).order_by(Source.created_at.desc()),
    )
    return list(result.scalars().all())


@router.post(
    "/notebooks/{notebook_id}/sources/upload",
    response_model=SourceOut,
    status_code=status.HTTP_201_CREATED,
)
async def upload_source(
    notebook_id: UUID,
    file: UploadFile,
    principal: Principal = Depends(current_principal),
    db: AsyncSession = Depends(get_db),
    arq: ArqRedis = Depends(get_arq),
) -> Source:
    # Cheap validation first — fail before any DB or storage I/O.
    if file.content_type != PDF_CONTENT_TYPE:
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            f"Only {PDF_CONTENT_TYPE} accepted in M1 (got {file.content_type!r}).",
        )
    data = await file.read()
    if len(data) == 0:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Empty file.")
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            f"File exceeds {MAX_UPLOAD_BYTES // (1024 * 1024)}MB limit.",
        )

    await _owned_notebook(notebook_id, principal, db)

    source_id = uuid4()
    key = f"org/{principal.org_id}/notebook/{notebook_id}/source/{source_id}/{file.filename}"
    bytes_uri = upload_bytes(key, data, content_type=PDF_CONTENT_TYPE)

    source = Source(
        id=source_id,
        notebook_id=notebook_id,
        kind="pdf",
        status="parsing",
        title=file.filename or "untitled.pdf",
        bytes_uri=bytes_uri,
        byte_size=len(data),
    )
    db.add(source)
    await db.flush()

    await arq.enqueue_job("parse_source", str(source_id))
    return source


@router.get("/sources/{source_id}", response_model=SourceOut)
async def get_source(
    source_id: UUID,
    principal: Principal = Depends(current_principal),
    db: AsyncSession = Depends(get_db),
) -> Source:
    return await _owned_source(source_id, principal, db)


@router.get("/sources/{source_id}/parts", response_model=list[SourcePartOut])
async def list_source_parts(
    source_id: UUID,
    principal: Principal = Depends(current_principal),
    db: AsyncSession = Depends(get_db),
) -> list[SourcePart]:
    await _owned_source(source_id, principal, db)
    result = await db.execute(
        select(SourcePart).where(SourcePart.source_id == source_id).order_by(SourcePart.ordinal),
    )
    return list(result.scalars().all())


@router.delete("/sources/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_source(
    source_id: UUID,
    principal: Principal = Depends(current_principal),
    db: AsyncSession = Depends(get_db),
) -> None:
    source = await _owned_source(source_id, principal, db)
    if source.bytes_uri:
        # Orphaning a blob is acceptable; row deletion must succeed.
        with suppress(Exception):
            s3_delete(source.bytes_uri)
    await db.delete(source)


# ---- file streaming (M5: PDF viewer fetches the original bytes) ----------


@router.get("/sources/{source_id}/file")
async def get_source_file(
    source_id: UUID,
    principal: Principal = Depends(current_principal),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """Stream the source's raw bytes (M5: PDF viewer in the browser).

    Auth-gated so the URL can't be guessed. The web wraps the response in a
    Blob and feeds it to react-pdf via createObjectURL; no presigned URLs needed
    in M5 (we'll switch to presign when files outgrow ~30MB).
    """
    source = await _owned_source(source_id, principal, db)
    if not source.bytes_uri:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Source has no stored bytes.")

    body, content_length, content_type = get_object_stream(source.bytes_uri)

    def _iter() -> Iterable[bytes]:
        # botocore's StreamingBody is sync; iter_chunks is the canonical accessor.
        yield from body.iter_chunks(chunk_size=1024 * 64)

    headers = {
        "Content-Disposition": f'inline; filename="{source.title}"',
        "Cache-Control": "private, max-age=3600",
    }
    if content_length is not None:
        headers["Content-Length"] = str(content_length)

    return StreamingResponse(
        _iter(),
        media_type=content_type or "application/pdf",
        headers=headers,
    )
