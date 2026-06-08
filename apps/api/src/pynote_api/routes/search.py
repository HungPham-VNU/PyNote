"""Search endpoint (M2: hybrid dense + sparse retrieval with RRF in SQL).

POST /api/v1/notebooks/{notebook_id}/search  body: {"q": "...", "k": 10}

Returns the top-K reranked chunks scoped to the notebook. The output shape is
intentionally what M3's prototype script and M4's chat graph will consume:
each hit carries the chunk identity, the source it came from, char offsets
(for citation roundtrip), and the fused score.
"""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import text as sql_text
from sqlalchemy.ext.asyncio import AsyncSession

from pynote_api.auth import Principal
from pynote_api.deps import current_principal, get_db
from pynote_core.embeddings import get_embedder
from pynote_core.models import Notebook

router = APIRouter(tags=["search"])

# RRF constant; 60 is the canonical value from the original paper (Cormack 2009).
RRF_K = 60
# Per-channel candidate pool sizes. Generous because rerank lands in M3 and
# downstream packing only takes top-K.
DENSE_LIMIT = 50
SPARSE_LIMIT = 50


class SearchRequest(BaseModel):
    q: str = Field(min_length=1, max_length=4000)
    k: int = Field(default=10, ge=1, le=50)


class SearchHit(BaseModel):
    chunk_id: UUID
    source_id: UUID
    source_part_id: UUID
    source_title: str | None = None
    page: int | None = None
    text: str
    char_start: int
    char_end: int
    score: float
    score_dense: float | None = None
    score_sparse: float | None = None


class SearchResponse(BaseModel):
    q: str
    k: int
    hits: list[SearchHit]


_HYBRID_SQL = sql_text(
    """
    WITH dense AS (
        SELECT id,
               (1 - (embedding <=> CAST(:qvec AS vector))) AS sim,
               ROW_NUMBER() OVER (ORDER BY embedding <=> CAST(:qvec AS vector)) AS rnk
        FROM chunk
        WHERE notebook_id = :nb AND embedding IS NOT NULL
        ORDER BY embedding <=> CAST(:qvec AS vector)
        LIMIT :dense_limit
    ),
    sparse AS (
        SELECT id,
               ts_rank_cd(tsv, q) AS sim,
               ROW_NUMBER() OVER (ORDER BY ts_rank_cd(tsv, q) DESC) AS rnk
        FROM chunk, websearch_to_tsquery('english', :qtext) AS q
        WHERE notebook_id = :nb AND tsv IS NOT NULL AND tsv @@ q
        ORDER BY ts_rank_cd(tsv, q) DESC
        LIMIT :sparse_limit
    ),
    fused AS (
        SELECT id,
               SUM(1.0 / (:rrf_k + rnk)) AS rrf,
               MAX(CASE WHEN src = 'd' THEN sim END) AS score_dense,
               MAX(CASE WHEN src = 's' THEN sim END) AS score_sparse
        FROM (
            SELECT id, rnk, sim, 'd' AS src FROM dense
            UNION ALL
            SELECT id, rnk, sim, 's' AS src FROM sparse
        ) t
        GROUP BY id
        ORDER BY rrf DESC
        LIMIT :k
    )
    SELECT c.id            AS chunk_id,
           c.source_id     AS source_id,
           c.source_part_id AS source_part_id,
           c.text          AS text,
           c.char_start    AS char_start,
           c.char_end      AS char_end,
           c.meta          AS meta,
           f.rrf           AS score,
           f.score_dense   AS score_dense,
           f.score_sparse  AS score_sparse
    FROM fused f
    JOIN chunk c ON c.id = f.id
    ORDER BY f.rrf DESC
    """,
)


@router.post("/notebooks/{notebook_id}/search", response_model=SearchResponse)
async def search_notebook(
    notebook_id: UUID,
    body: SearchRequest,
    principal: Principal = Depends(current_principal),
    db: AsyncSession = Depends(get_db),
) -> SearchResponse:
    notebook = await db.get(Notebook, notebook_id)
    if notebook is None or notebook.org_id != principal.org_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Notebook not found.")

    embedder = get_embedder()
    qvec = await embedder.embed_one(body.q)

    # pgvector accepts a string literal like '[0.1, 0.2, ...]'.
    qvec_literal = "[" + ",".join(f"{x:.6f}" for x in qvec) + "]"

    result = await db.execute(
        _HYBRID_SQL,
        {
            "nb": str(notebook_id),
            "qvec": qvec_literal,
            "qtext": body.q,
            "dense_limit": DENSE_LIMIT,
            "sparse_limit": SPARSE_LIMIT,
            "rrf_k": RRF_K,
            "k": body.k,
        },
    )
    rows = result.mappings().all()

    hits = [
        SearchHit(
            chunk_id=r["chunk_id"],
            source_id=r["source_id"],
            source_part_id=r["source_part_id"],
            source_title=_pluck(r["meta"], "source_title"),
            page=_pluck(r["meta"], "page"),
            text=r["text"],
            char_start=r["char_start"],
            char_end=r["char_end"],
            score=float(r["score"]),
            score_dense=_maybe_float(r["score_dense"]),
            score_sparse=_maybe_float(r["score_sparse"]),
        )
        for r in rows
    ]
    return SearchResponse(q=body.q, k=body.k, hits=hits)


def _pluck(meta: Any, key: str) -> Any:
    if isinstance(meta, dict):
        return meta.get(key)
    return None


def _maybe_float(v: Any) -> float | None:
    return float(v) if v is not None else None
