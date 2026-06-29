"""arq task functions.

M0: noop_task, ping_llm_task.
M1: parse_source — downloads a source's bytes, parses it, persists SourceParts.
M2 will add embed_source; M3 onward, more.
"""

import asyncio
import logging
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import UUID

from langchain_core.messages import HumanMessage
from sqlalchemy import select
from sqlalchemy import text as sql_text

if TYPE_CHECKING:
    from arq.connections import ArqRedis

from pynote_core.chunker import chunk_text
from pynote_core.db import async_session_scope
from pynote_core.embeddings import get_embedder
from pynote_core.llm import get_chat_model
from pynote_core.mindmap import generate_mind_map
from pynote_core.models import Chunk, Notebook, Source, SourcePart
from pynote_core.outliner import generate_outline
from pynote_core.parsers import ParsedPart
from pynote_core.parsers import parse as parse_source_file
from pynote_core.storage import download_to_path

log = logging.getLogger("pynote_worker.tasks")


async def noop_task(ctx: dict[str, Any]) -> dict[str, Any]:
    """Used by tests to confirm the worker is alive."""
    return {"ok": True, "at": datetime.now(UTC).isoformat()}


async def ping_llm_task(ctx: dict[str, Any], prompt: str = "ping") -> dict[str, Any]:
    """End-to-end smoke: routes through the configured chat model and traces to LangSmith."""
    model = get_chat_model()
    resp = await model.ainvoke([HumanMessage(content=prompt)])
    return {"ok": True, "reply": str(resp.content)[:500]}


async def parse_source(ctx: dict[str, Any], source_id: str) -> dict[str, Any]:
    """Download → parse → insert SourceParts → mark `parsed` (or `failed`).

    Idempotent: re-running clears prior parts before re-inserting.
    Emits one log line per phase so each parse is easy to follow in the worker terminal.
    """
    sid = UUID(source_id)
    started = time.perf_counter()
    log.info("parse_source[%s]: start", sid)

    async with async_session_scope() as db:
        source = await db.get(Source, sid)
        if source is None:
            log.warning("parse_source[%s]: source row missing — nothing to do", sid)
            return {"ok": False, "reason": "source-not-found", "source_id": source_id}
        if not source.bytes_uri:
            log.error("parse_source[%s]: bytes_uri is empty — marking failed", sid)
            source.status = "failed"
            source.error = "bytes_uri is empty"
            return {"ok": False, "reason": "missing-bytes-uri"}

        kind, uri, title, byte_size = source.kind, source.bytes_uri, source.title, source.byte_size

    log.info(
        "parse_source[%s]: title=%r kind=%s size=%s uri=%s",
        sid,
        title,
        kind,
        _fmt_bytes(byte_size),
        uri,
    )

    download_started = time.perf_counter()
    try:
        parts = await asyncio.to_thread(_download_and_parse, uri, kind)
    except Exception as e:
        log.exception("parse_source[%s]: parse failed", sid)
        async with async_session_scope() as db:
            source = await db.get(Source, sid)
            if source is not None:
                source.status = "failed"
                source.error = f"{type(e).__name__}: {e}"[:1000]
        return {"ok": False, "reason": "parse-failed", "error": str(e)[:200]}
    parse_ms = int((time.perf_counter() - download_started) * 1000)
    total_chars = sum(len(p.text) for p in parts)
    empty_parts = sum(1 for p in parts if not p.text.strip())
    log.info(
        "parse_source[%s]: parsed %d parts in %dms (%d chars total, %d empty)",
        sid,
        len(parts),
        parse_ms,
        total_chars,
        empty_parts,
    )

    persist_started = time.perf_counter()
    async with async_session_scope() as db:
        source = await db.get(Source, sid)
        if source is None:
            log.warning("parse_source[%s]: source vanished while parsing — discarding parts", sid)
            return {"ok": False, "reason": "source-vanished"}

        existing = list(await _existing_parts(db, sid))
        if existing:
            log.info("parse_source[%s]: clearing %d existing parts (re-run)", sid, len(existing))
            for old in existing:
                await db.delete(old)
            await db.flush()

        for p in parts:
            db.add(
                SourcePart(
                    source_id=sid,
                    ordinal=p.ordinal,
                    page=p.page,
                    text=p.text,
                    bbox=p.bbox,
                )
            )
        source.status = "parsed"
        source.error = None
    persist_ms = int((time.perf_counter() - persist_started) * 1000)

    total_ms = int((time.perf_counter() - started) * 1000)
    log.info(
        "parse_source[%s]: done — status=parsed parts=%d persist=%dms total=%dms",
        sid,
        len(parts),
        persist_ms,
        total_ms,
    )

    # M2: hand off to embedding. Worker has ctx['redis'] (arq's pool) for self-enqueue.
    arq: ArqRedis | None = ctx.get("redis")
    if arq is not None:
        await arq.enqueue_job("embed_source", source_id)
        log.info("parse_source[%s]: enqueued embed_source", sid)

    return {"ok": True, "source_id": source_id, "parts": len(parts)}


async def embed_source(ctx: dict[str, Any], source_id: str) -> dict[str, Any]:
    """Chunk → embed → persist with tsvector. Marks source `ready` (or `failed`).

    Idempotent: clears prior chunks for this source before re-inserting.
    """
    sid = UUID(source_id)
    started = time.perf_counter()
    log.info("embed_source[%s]: start", sid)

    async with async_session_scope() as db:
        source = await db.get(Source, sid)
        if source is None:
            log.warning("embed_source[%s]: source row missing", sid)
            return {"ok": False, "reason": "source-not-found"}
        if source.status != "parsed":
            log.warning(
                "embed_source[%s]: skipping — status=%s (expected 'parsed')",
                sid,
                source.status,
            )
            return {"ok": False, "reason": f"unexpected-status:{source.status}"}

        notebook_id = source.notebook_id
        source.status = "embedding"

        # Load parts ordered.
        parts_result = await db.execute(
            select(SourcePart).where(SourcePart.source_id == sid).order_by(SourcePart.ordinal),
        )
        parts = list(parts_result.scalars().all())

    if not parts:
        log.warning("embed_source[%s]: no parts to embed", sid)
        async with async_session_scope() as db:
            src = await db.get(Source, sid)
            if src is not None:
                src.status = "ready"
        return {"ok": True, "chunks": 0}

    # ---- 1. Chunk every part (CPU work — to_thread keeps loop free) ----
    chunk_phase = time.perf_counter()
    all_chunks: list[tuple[SourcePart, int, Any]] = []  # (part, ordinal_in_source, Chunk)
    ordinal = 0
    for part in parts:
        for c in chunk_text(part.text):
            all_chunks.append((part, ordinal, c))
            ordinal += 1
    log.info(
        "embed_source[%s]: produced %d chunks from %d parts in %dms",
        sid,
        len(all_chunks),
        len(parts),
        int((time.perf_counter() - chunk_phase) * 1000),
    )

    if not all_chunks:
        async with async_session_scope() as db:
            src = await db.get(Source, sid)
            if src is not None:
                src.status = "ready"
        log.info("embed_source[%s]: nothing to embed (empty text)", sid)
        return {"ok": True, "chunks": 0}

    # ---- 2. Embed in one batched call ----
    embed_phase = time.perf_counter()
    embedder = get_embedder()
    texts = [c.text for (_, _, c) in all_chunks]
    vectors = await embedder.embed_many(texts)
    log.info(
        "embed_source[%s]: embedded %d chunks in %dms (%d-dim)",
        sid,
        len(vectors),
        int((time.perf_counter() - embed_phase) * 1000),
        len(vectors[0]) if vectors else 0,
    )

    # ---- 3. Persist + tsvector via SQL ----
    persist_phase = time.perf_counter()
    async with async_session_scope() as db:
        src = await db.get(Source, sid)
        if src is None:
            log.warning("embed_source[%s]: source vanished mid-embed — discarding", sid)
            return {"ok": False, "reason": "source-vanished"}

        # Idempotent: drop existing chunks for this source.
        existing = await db.execute(select(Chunk).where(Chunk.source_id == sid))
        old = list(existing.scalars().all())
        if old:
            log.info("embed_source[%s]: clearing %d existing chunks (re-run)", sid, len(old))
            for o in old:
                await db.delete(o)
            await db.flush()

        for (part, ord_in_src, c), vec in zip(all_chunks, vectors, strict=True):
            db.add(
                Chunk(
                    notebook_id=notebook_id,
                    source_id=sid,
                    source_part_id=part.id,
                    level=0,
                    ordinal=ord_in_src,
                    text=c.text,
                    char_start=c.char_start,
                    char_end=c.char_end,
                    embedding=vec,
                    meta={"page": part.page, "source_title": src.title},
                ),
            )
        await db.flush()

        # Populate tsvector once per source (one round-trip, indexed by GIN).
        await db.execute(
            sql_text(
                "UPDATE chunk SET tsv = to_tsvector('english', text) "
                "WHERE source_id = :sid AND tsv IS NULL",
            ),
            {"sid": str(sid)},
        )

        src.status = "ready"
        src.error = None

    total_ms = int((time.perf_counter() - started) * 1000)
    log.info(
        "embed_source[%s]: done — status=ready chunks=%d persist=%dms total=%dms",
        sid,
        len(all_chunks),
        int((time.perf_counter() - persist_phase) * 1000),
        total_ms,
    )

    # M6: enqueue best-effort outline generation. Failure does not flip the
    # source out of `ready` — the source remains usable without suggestions.
    arq: ArqRedis | None = ctx.get("redis")
    if arq is not None:
        await arq.enqueue_job("outline_source", source_id)
        log.info("embed_source[%s]: enqueued outline_source", sid)

    return {"ok": True, "source_id": source_id, "chunks": len(all_chunks)}


async def outline_source(ctx: dict[str, Any], source_id: str) -> dict[str, Any]:
    """Generate `{abstract, key_entities, suggested_questions}` and persist on meta.

    Best-effort: a model or parse failure logs and exits 0 rather than retrying,
    because the outline is decorative — the source is fully usable without it.
    """
    sid = UUID(source_id)
    started = time.perf_counter()
    log.info("outline_source[%s]: start", sid)

    # Pull joined text from source parts (the chunker is per-part in M2, but for
    # outlining we want continuous prose — concat with double-newlines).
    async with async_session_scope() as db:
        source = await db.get(Source, sid)
        if source is None:
            return {"ok": False, "reason": "source-not-found"}
        parts_result = await db.execute(
            select(SourcePart).where(SourcePart.source_id == sid).order_by(SourcePart.ordinal),
        )
        parts = list(parts_result.scalars().all())

    joined = "\n\n".join(p.text for p in parts if p.text).strip()
    if not joined:
        log.info("outline_source[%s]: empty text — nothing to outline", sid)
        return {"ok": True, "reason": "empty"}

    try:
        outline = await generate_outline(joined)
    except Exception as e:
        log.warning("outline_source[%s]: generation failed: %s", sid, e)
        return {"ok": False, "reason": "generation-failed", "error": str(e)[:200]}

    async with async_session_scope() as db:
        src = await db.get(Source, sid)
        if src is None:
            return {"ok": False, "reason": "source-vanished"}
        src.meta = {
            **(src.meta or {}),
            "abstract": outline.abstract,
            "key_entities": outline.key_entities,
            "suggested_questions": outline.suggested_questions,
        }

    total_ms = int((time.perf_counter() - started) * 1000)
    log.info(
        "outline_source[%s]: done — %d entities, %d questions in %dms",
        sid,
        len(outline.key_entities),
        len(outline.suggested_questions),
        total_ms,
    )
    return {
        "ok": True,
        "source_id": source_id,
        "n_entities": len(outline.key_entities),
        "n_questions": len(outline.suggested_questions),
    }


async def generate_mind_map_task(ctx: dict[str, Any], notebook_id: str) -> dict[str, Any]:
    """Generate a mind map (M12) and persist on `notebook.settings["mind_map"]`.

    Status lives inside the same key so the API can poll it: `generating` is
    written synchronously by the route before this job is enqueued, this task
    overwrites it with `ready` + the map, or `failed` + an error string.
    """
    nbid = UUID(notebook_id)
    started = time.perf_counter()
    log.info("generate_mind_map_task[%s]: start", nbid)

    async with async_session_scope() as db:
        rows = await db.execute(
            select(SourcePart, Source.title)
            .join(Source, Source.id == SourcePart.source_id)
            .where(Source.notebook_id == nbid, Source.status == "ready")
            .order_by(Source.created_at, SourcePart.ordinal),
        )
        parts = [(part, title) for part, title in rows.all()]

    if not parts:
        log.warning("generate_mind_map_task[%s]: no ready sources", nbid)
        async with async_session_scope() as db:
            notebook = await db.get(Notebook, nbid)
            if notebook is not None:
                notebook.settings = {
                    **(notebook.settings or {}),
                    "mind_map": {"status": "failed", "error": "No ready sources."},
                }
        return {"ok": False, "reason": "no-ready-sources"}

    try:
        mind_map = await generate_mind_map(parts)
    except Exception as e:
        log.exception("generate_mind_map_task[%s]: generation failed", nbid)
        async with async_session_scope() as db:
            notebook = await db.get(Notebook, nbid)
            if notebook is not None:
                notebook.settings = {
                    **(notebook.settings or {}),
                    "mind_map": {
                        "status": "failed",
                        "error": f"{type(e).__name__}: {str(e)[:200]}",
                    },
                }
        return {"ok": False, "reason": "generation-failed", "error": str(e)[:200]}

    payload = {
        "status": "ready",
        "generated_at": datetime.now(UTC).isoformat(),
        **mind_map.model_dump(mode="json", by_alias=True),
    }
    async with async_session_scope() as db:
        notebook = await db.get(Notebook, nbid)
        if notebook is None:
            log.warning("generate_mind_map_task[%s]: notebook vanished", nbid)
            return {"ok": False, "reason": "notebook-vanished"}
        notebook.settings = {**(notebook.settings or {}), "mind_map": payload}

    total_ms = int((time.perf_counter() - started) * 1000)
    log.info(
        "generate_mind_map_task[%s]: done — %d nodes, %d edges in %dms",
        nbid,
        len(mind_map.nodes),
        len(mind_map.edges),
        total_ms,
    )
    return {"ok": True, "nodes": len(mind_map.nodes), "edges": len(mind_map.edges)}


# ---- internals -------------------------------------------------------------


def _download_and_parse(uri: str, kind: str) -> list[ParsedPart]:
    with tempfile.TemporaryDirectory(prefix="pynote-parse-") as tmp:
        local = Path(tmp) / "source.bin"
        download_to_path(uri, local)
        return parse_source_file(kind, local)


async def _existing_parts(db: Any, source_id: UUID) -> Any:
    result = await db.execute(select(SourcePart).where(SourcePart.source_id == source_id))
    return result.scalars().all()


def _fmt_bytes(n: int | None) -> str:
    if n is None:
        return "?"
    if n < 1024:
        return f"{n}B"
    if n < 1024 * 1024:
        return f"{n / 1024:.1f}KB"
    return f"{n / (1024 * 1024):.1f}MB"
