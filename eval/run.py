"""M7 eval runner — the v1 ship gate.

Run a JSONL of questions against a notebook, produce per-question metrics and
a summary verdict. Designed for tight feedback loops on free tier, with the
optional Ragas integration for ship-eligible runs.

Input JSONL — one record per question:
    {"q": "...", "selection": "?", "reference": "?"}
    - q:         required
    - selection: optional, treated as user-highlighted context
    - reference: optional, ground-truth answer — enables Ragas context_recall

Output JSONL — one record per question + one trailing `_summary`:
    {"i": N, "q": ..., "answer": ..., "n_citations": ..., "citation_grounding": ...,
     "faithfulness_lite": ..., "answer_relevancy_lite": ...,
     "ragas": {"faithfulness": ..., "answer_relevancy": ..., ...}?, ...}
    {"_summary": true, "n": N, "avg": {...}, "passed": bool, "config": {...}}

Usage:
    uv run python -m eval.run --notebook UUID --file eval/golden/sample.jsonl \\
        > eval/results/m7-$(date +%Y%m%d-%H%M%S).jsonl
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from eval.metrics import GateResult, aggregate, citation_grounding, lite_scores
from eval.prototype.chat import ask as ask_once
from eval.ragas_metrics import is_available as ragas_available
from pynote_core.tracing import configure_tracing

# ---- IO --------------------------------------------------------------------


def _emit(record: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(record, default=str) + "\n")
    sys.stdout.flush()


def _print_progress(msg: str) -> None:
    """Progress goes to stderr so stdout stays clean JSONL."""
    sys.stderr.write(msg + "\n")
    sys.stderr.flush()


# ---- core run --------------------------------------------------------------


async def _run_one(notebook_id: UUID, q: dict[str, Any], top_k: int) -> dict[str, Any]:
    """One question → answer + per-row metrics."""
    answer, hits = await ask_once(
        notebook_id,
        q["q"],
        selection=q.get("selection"),
        top_k=top_k,
    )
    contexts = [h.text for h in hits]
    cited_texts = [c.cited_text for c in answer.citations]

    cg = citation_grounding(answer)
    lite = lite_scores(q["q"], contexts, answer.text, cited_texts)

    return {
        "q": q["q"],
        "answer": answer.text,
        "contexts": contexts,
        "reference": q.get("reference"),
        "n_citations": len(answer.citations),
        "citation_grounding": cg,
        "faithfulness_lite": lite.faithfulness,
        "answer_relevancy_lite": lite.answer_relevancy,
        "grounding_overlap": lite.grounding_overlap,
        "ungrounded": [c.cited_text for c in answer.citations if not c.roundtrip_ok],
    }


async def run(
    notebook_id: UUID,
    questions: list[dict[str, Any]],
    *,
    top_k: int,
    with_ragas: bool,
) -> tuple[list[dict[str, Any]], GateResult]:
    rows: list[dict[str, Any]] = []
    for i, q in enumerate(questions):
        _print_progress(f"[{i + 1}/{len(questions)}] {q['q'][:60]}…")
        try:
            row = await _run_one(notebook_id, q, top_k)
            row["i"] = i
            row["error"] = None
        except Exception as e:
            row = {
                "i": i,
                "q": q["q"],
                "answer": None,
                "contexts": [],
                "n_citations": 0,
                "citation_grounding": 0.0,
                "faithfulness_lite": 0.0,
                "answer_relevancy_lite": 0.0,
                "grounding_overlap": 0.0,
                "error": str(e)[:200],
            }
        rows.append(row)
        # With Ragas enabled, rows are emitted after scoring so the JSONL
        # actually contains the ragas block (emitting here would drop it).
        if not with_ragas:
            _emit({k: v for k, v in row.items() if k != "contexts"})

    if with_ragas:
        from eval.ragas_metrics import score_with_ragas

        _print_progress("Running Ragas metrics (this calls the judge model)…")
        try:
            ragas_out = await score_with_ragas(rows)
            for row, rs in zip(rows, ragas_out, strict=False):
                row["ragas"] = {
                    "faithfulness": rs.faithfulness,
                    "answer_relevancy": rs.answer_relevancy,
                    "context_precision": rs.context_precision,
                    "context_recall": rs.context_recall,
                }
        except Exception as e:
            _print_progress(f"Ragas scoring failed: {e}")
        for row in rows:
            _emit({k: v for k, v in row.items() if k != "contexts"})

    gate = aggregate(rows)
    return rows, gate


# ---- CLI -------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="eval.run", description="M7 v1 ship-gate runner")
    p.add_argument("--notebook", required=True, help="Notebook UUID")
    p.add_argument("--file", required=True, help="Path to JSONL of {q, selection?, reference?}")
    p.add_argument("--top-k", type=int, default=8, dest="top_k")
    p.add_argument(
        "--with-ragas",
        action="store_true",
        help="Run Ragas metrics (requires `ragas` installed; uses cheap judge model)",
    )
    return p


async def _main_async(argv: list[str] | None) -> int:
    args = _build_parser().parse_args(argv)
    configure_tracing()

    path = Path(args.file)
    if not path.exists():
        _print_progress(f"file not found: {path}")
        return 2

    questions = [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]
    if not questions:
        _print_progress(f"no questions in {path}")
        return 2

    want_ragas = args.with_ragas
    if want_ragas and not ragas_available():
        _print_progress(
            "Ragas not installed (`uv pip install --group eval`) — continuing with lite metrics only.",
        )
        want_ragas = False

    _rows, gate = await run(
        UUID(args.notebook),
        questions,
        top_k=args.top_k,
        with_ragas=want_ragas,
    )

    summary = {
        "_summary": True,
        "n": gate.n,
        "passed": gate.passed,
        "avg": {
            "citation_grounding": gate.citation_grounding_avg,
            "faithfulness_lite": gate.faithfulness_lite_avg,
            "answer_relevancy_lite": gate.answer_relevancy_lite_avg,
        },
        "config": {
            "notebook": args.notebook,
            "top_k": args.top_k,
            "with_ragas": want_ragas,
            "started_at": datetime.now(UTC).isoformat(),
        },
    }
    _emit(summary)

    _print_progress(
        f"\nGATE: {'PASS' if gate.passed else 'FAIL'}  "
        f"cg={gate.citation_grounding_avg:.2%}  "
        f"fl={gate.faithfulness_lite_avg:.2%}  "
        f"ar={gate.answer_relevancy_lite_avg:.2%}",
    )
    return 0 if gate.passed else 1


def main(argv: list[str] | None = None) -> int:
    import sys as _sys

    if _sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    return asyncio.run(_main_async(argv))


if __name__ == "__main__":
    raise SystemExit(main())
