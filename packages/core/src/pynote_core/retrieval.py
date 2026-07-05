"""Hybrid retrieval + Voyage rerank.

The shared layer used by:
  - /api/v1/notebooks/{id}/search        (one-shot retrieval)
  - eval/prototype/m3.py                  (CLI grading)
  - pynote_core.chat_graph                (M4 chat)

`hybrid_retrieve` runs the same RRF CTE the search endpoint uses, but as a
plain async function so it can be called outside FastAPI.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from sqlalchemy import text as sql_text

from pynote_core.db import async_session_scope
from pynote_core.embeddings import get_embedder
from pynote_core.settings import get_settings

if TYPE_CHECKING:
    from collections.abc import Sequence
    from uuid import UUID


@dataclass(frozen=True, slots=True)
class Hit:
    """One retrieval hit, normalized for downstream packing."""

    chunk_id: UUID
    source_id: UUID
    source_part_id: UUID
    source_title: str | None
    page: int | None
    text: str
    char_start: int  # offsets into source_part.text — the citation contract anchor
    char_end: int
    score: float
    score_dense: float | None = None
    score_sparse: float | None = None


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
               SUM(1.0 / (60 + rnk)) AS rrf,
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
    SELECT c.id, c.source_id, c.source_part_id, c.text,
           c.char_start, c.char_end, c.meta,
           f.rrf AS score, f.score_dense, f.score_sparse
    FROM fused f
    JOIN chunk c ON c.id = f.id
    ORDER BY f.rrf DESC
    """,
)


async def hybrid_retrieve(notebook_id: UUID, query: str, *, k: int = 50) -> list[Hit]:
    """RRF over pgvector + tsvector, scoped to one notebook."""
    embedder = get_embedder()
    qvec = await embedder.embed_one(query)
    qvec_literal = "[" + ",".join(f"{x:.6f}" for x in qvec) + "]"

    async with async_session_scope() as db:
        result = await db.execute(
            _HYBRID_SQL,
            {
                "nb": str(notebook_id),
                "qvec": qvec_literal,
                "qtext": query,
                "dense_limit": 50,
                "sparse_limit": 50,
                "k": k,
            },
        )
        rows = result.mappings().all()

    out: list[Hit] = []
    for r in rows:
        meta = r["meta"] if isinstance(r["meta"], dict) else {}
        out.append(
            Hit(
                chunk_id=r["id"],
                source_id=r["source_id"],
                source_part_id=r["source_part_id"],
                source_title=meta.get("source_title"),
                page=meta.get("page"),
                text=r["text"],
                char_start=r["char_start"],
                char_end=r["char_end"],
                score=float(r["score"]),
                score_dense=float(r["score_dense"]) if r["score_dense"] is not None else None,
                score_sparse=float(r["score_sparse"]) if r["score_sparse"] is not None else None,
            )
        )
    return out


async def rerank(query: str, hits: Sequence[Hit], *, top_k: int = 8) -> list[Hit]:
    """Voyage rerank-2.5 if VOYAGE_API_KEY is set; otherwise the top_k input as-is."""
    if not hits:
        return []
    settings = get_settings()
    if not settings.voyage_api_key:
        return list(hits[:top_k])

    from langchain_core.documents import Document
    from langchain_voyageai import VoyageAIRerank

    reranker = VoyageAIRerank(  # type: ignore[call-arg]
        model=settings.rerank_model,
        voyageai_api_key=settings.voyage_api_key,
        top_k=top_k,
    )
    docs = [
        Document(page_content=h.text, metadata={"idx": i, "chunk_id": str(h.chunk_id)})
        for i, h in enumerate(hits)
    ]
    reranked = await reranker.acompress_documents(docs, query)

    out: list[Hit] = []
    for d in reranked:
        idx = d.metadata.get("idx")
        if idx is None:
            continue
        original = hits[idx]
        out.append(
            Hit(
                chunk_id=original.chunk_id,
                source_id=original.source_id,
                source_part_id=original.source_part_id,
                source_title=original.source_title,
                page=original.page,
                text=original.text,
                char_start=original.char_start,
                char_end=original.char_end,
                score=float(d.metadata.get("relevance_score", original.score)),
                score_dense=original.score_dense,
                score_sparse=original.score_sparse,
            )
        )
    return out
