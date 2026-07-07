"""Retrieval-level eval — recall@k and MRR per pipeline stage. No LLM calls.

Answers the question the end-to-end gate can't: when a question fails, did
retrieval miss or did generation ignore? Scores four stages independently:

    dense       pgvector-only ranking (derived from score_dense)
    sparse      tsvector-only ranking (derived from score_sparse)
    hybrid      the fused RRF order (what hybrid_retrieve returns)
    packed      post-rerank + overlap-dedup — the top-8 the model actually sees

Input JSONL — one record per question:
    {"q": "...", "gold_spans": [{"must_contain": "exact substring",
                                 "source_title": "...?", "page": 4?}]}
    - q:            required
    - gold_spans:   required (rows without it are skipped) — a retrieved chunk
                    counts as gold if its text contains `must_contain`
                    (whitespace-normalized, case-insensitive) AND matches
                    page / source_title when those are given. Substring labels
                    survive re-chunking; chunk IDs don't.

Output JSONL — one row per question + a trailing `_summary` with per-stage
recall@{5,8,20,50} and MRR averages.

Usage:
    uv run python -m eval.retrieval_eval --notebook UUID \\
        --file eval/golden/retrieval.jsonl > eval/results/retrieval-$(date +%Y%m%d-%H%M%S).jsonl
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from pynote_core.retrieval import Hit, dedup_overlaps, hybrid_retrieve, rerank

RECALL_KS = (5, 8, 20, 50)
STAGES = ("dense", "sparse", "hybrid", "packed")

# Over-fetch so the derived dense/sparse rankings are complete for the top-50
# of each leg (the CTE's dense_limit/sparse_limit) despite the fused LIMIT.
FETCH_K = 100


# ---- gold matching ----------------------------------------------------------

_WS = re.compile(r"\s+")


def _norm(text: str) -> str:
    return _WS.sub(" ", text).strip().casefold()


def _matches(hit: Hit, span: dict[str, Any]) -> bool:
    needle = _norm(str(span.get("must_contain", "")))
    if not needle or needle not in _norm(hit.text):
        return False
    if span.get("page") is not None and hit.page != span["page"]:
        return False
    title = span.get("source_title")
    return title is None or (hit.source_title or "") == title


def _first_gold_rank(hits: list[Hit], gold_spans: list[dict[str, Any]]) -> int | None:
    """1-based rank of the first hit matching any gold span, or None."""
    for i, h in enumerate(hits):
        if any(_matches(h, s) for s in gold_spans):
            return i + 1
    return None


# ---- stage rankings ----------------------------------------------------------


def _stage_rankings(fused: list[Hit], packed: list[Hit]) -> dict[str, list[Hit]]:
    dense = sorted(
        (h for h in fused if h.score_dense is not None),
        key=lambda h: h.score_dense or 0.0,
        reverse=True,
    )
    sparse = sorted(
        (h for h in fused if h.score_sparse is not None),
        key=lambda h: h.score_sparse or 0.0,
        reverse=True,
    )
    return {"dense": dense, "sparse": sparse, "hybrid": fused, "packed": packed}


# ---- IO ----------------------------------------------------------------------


def _emit(record: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(record, default=str) + "\n")
    sys.stdout.flush()


def _print_progress(msg: str) -> None:
    sys.stderr.write(msg + "\n")
    sys.stderr.flush()


# ---- core run ------------------------------------------------------------------


async def _run_one(notebook_id: UUID, q: dict[str, Any]) -> dict[str, Any]:
    fused = await hybrid_retrieve(notebook_id, q["q"], k=FETCH_K)
    reranked = await rerank(q["q"], fused[:50], top_k=50)
    packed = dedup_overlaps(reranked, top_k=8)

    rankings = _stage_rankings(fused, packed)
    gold = q["gold_spans"]

    row: dict[str, Any] = {"q": q["q"], "n_retrieved": len(fused)}
    for stage in STAGES:
        rank = _first_gold_rank(rankings[stage], gold)
        row[f"{stage}_rank"] = rank
        row[f"{stage}_rr"] = (1.0 / rank) if rank else 0.0
        for k in RECALL_KS:
            if stage == "packed" and k > 8:
                continue  # packed is capped at 8 by construction
            row[f"{stage}_recall@{k}"] = 1.0 if (rank is not None and rank <= k) else 0.0
    return row


async def run(notebook_id: UUID, questions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for i, q in enumerate(questions):
        _print_progress(f"[{i + 1}/{len(questions)}] {q['q'][:60]}…")
        try:
            row = await _run_one(notebook_id, q)
            row["i"] = i
            row["error"] = None
        except Exception as e:
            row = {"i": i, "q": q["q"], "error": str(e)[:200]}
        rows.append(row)
        _emit(row)
    return rows


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    scored = [r for r in rows if r.get("error") is None]
    n = len(scored)
    avg: dict[str, float] = {}
    if n:
        for stage in STAGES:
            avg[f"{stage}_mrr"] = sum(r.get(f"{stage}_rr", 0.0) for r in scored) / n
            for k in RECALL_KS:
                key = f"{stage}_recall@{k}"
                if any(key in r for r in scored):
                    avg[key] = sum(r.get(key, 0.0) for r in scored) / n
    return {
        "_summary": True,
        "n": n,
        "n_errors": len(rows) - n,
        "avg": avg,
        "config": {
            "fetch_k": FETCH_K,
            "recall_ks": list(RECALL_KS),
            "started_at": datetime.now(UTC).isoformat(),
        },
    }


# ---- CLI -----------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="eval.retrieval_eval",
        description="Retrieval-stage recall@k / MRR runner (no LLM)",
    )
    p.add_argument("--notebook", required=True, help="Notebook UUID")
    p.add_argument("--file", required=True, help="JSONL of {q, gold_spans}")
    return p


async def _main_async(argv: list[str] | None) -> int:
    args = _build_parser().parse_args(argv)

    path = Path(args.file)
    if not path.exists():
        _print_progress(f"file not found: {path}")
        return 2

    records = [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]
    questions = [r for r in records if r.get("gold_spans")]
    skipped = len(records) - len(questions)
    if skipped:
        _print_progress(f"skipping {skipped} record(s) without gold_spans")
    if not questions:
        _print_progress(f"no records with gold_spans in {path}")
        return 2

    rows = await run(UUID(args.notebook), questions)
    summary = summarize(rows)
    _emit(summary)

    avg = summary["avg"]
    _print_progress(
        "\nRETRIEVAL  "
        + "  ".join(
            f"{stage}: r@8={avg.get(f'{stage}_recall@8', 0.0):.2%} "
            f"mrr={avg.get(f'{stage}_mrr', 0.0):.3f}"
            for stage in STAGES
        )
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    return asyncio.run(_main_async(argv))


if __name__ == "__main__":
    raise SystemExit(main())
