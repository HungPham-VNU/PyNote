"""M3 prototype CLI — proves Anthropic Citations API roundtrip on real PDFs.

Each subcommand implements one of the 5 smoke cases from PLAN.md M3:
    health    | all providers reachable
    ask       | basic grounded Q with citations
    chat      | multi-turn follow-up (citations across turns)
    select    | user-selected text is treated as context
    stability | same query twice yields stable top hits
    bulk      | run a golden set, report fidelity % across questions

Usage:
    uv run python -m eval.prototype.m3 health
    uv run python -m eval.prototype.m3 ask     --notebook UUID --q "..."
    uv run python -m eval.prototype.m3 chat    --notebook UUID --turns "q1" "q2" "q3"
    uv run python -m eval.prototype.m3 select  --notebook UUID --selection "..." --q "..."
    uv run python -m eval.prototype.m3 stability --notebook UUID --q "..." --runs 3
    uv run python -m eval.prototype.m3 bulk    --notebook UUID --file eval/golden/sample.jsonl
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

from eval.prototype.chat import ask as ask_once
from eval.prototype.citations import ParsedAnswer, fidelity
from eval.prototype.retrieval import hybrid_retrieve
from pynote_core.settings import get_settings
from pynote_core.tracing import configure_tracing

# ---- output helpers --------------------------------------------------------


def _print_answer(answer: ParsedAnswer) -> None:
    print("\n--- answer ---")
    print(answer.text or "<empty>")
    print(f"\n--- citations: {len(answer.citations)} (fidelity={fidelity(answer):.2%}) ---")
    for i, c in enumerate(answer.citations):
        ok = "✓" if c.roundtrip_ok else "✗"
        cited = c.cited_text.replace("\n", " ")[:80]
        print(f"  [{i}] {ok} chunk={c.chunk_id} idx={c.search_result_index} «{cited}»")


def _emit(record: dict[str, Any]) -> None:
    """JSONL line to stdout — useful for bulk-grading pipelines."""
    sys.stdout.write(json.dumps(record, default=str) + "\n")
    sys.stdout.flush()


# ---- subcommands -----------------------------------------------------------


async def cmd_health(_: argparse.Namespace) -> int:
    settings = get_settings()
    status = {
        "anthropic_base_url": settings.anthropic_base_url,
        "anthropic_key": _present(settings.anthropic_api_key),
        "embedding_provider": settings.embedding_provider,
        "embedding_dim": settings.embedding_dim,
        "voyage_key": _present(settings.voyage_api_key),
        "rerank_active": bool(settings.voyage_api_key),
        "langsmith_tracing": bool(settings.langsmith_tracing and settings.langsmith_api_key),
    }

    # DB reachability + chunk count
    from sqlalchemy import text as sql_text

    from pynote_core.db import async_session_scope

    try:
        async with async_session_scope() as db:
            r = await db.execute(sql_text("SELECT COUNT(*) FROM chunk"))
            status["postgres"] = "ok"
            status["chunks_total"] = int(r.scalar() or 0)
    except Exception as e:
        status["postgres"] = f"down: {e}"

    print(json.dumps(status, indent=2))
    needs_attention = (
        status["anthropic_key"] != "set"
        or status.get("postgres") != "ok"
        or status.get("chunks_total", 0) == 0
    )
    return 1 if needs_attention else 0


async def cmd_ask(args: argparse.Namespace) -> int:
    answer, hits = await ask_once(UUID(args.notebook), args.q, top_k=args.top_k)
    print(f"retrieved {len(hits)} hits, top score={hits[0].score:.3f}" if hits else "no hits")
    _print_answer(answer)
    return 0


async def cmd_chat(args: argparse.Namespace) -> int:
    history: list[dict[str, Any]] = []
    last: ParsedAnswer | None = None
    for i, turn in enumerate(args.turns):
        print(f"\n=== turn {i + 1}: {turn!r} ===")
        answer, _ = await ask_once(UUID(args.notebook), turn, history=history, top_k=args.top_k)
        _print_answer(answer)
        # Carry the model's reply (without citations) into history as plain text;
        # full history fidelity isn't the point here — context preservation is.
        history.append({"role": "user", "content": turn})
        history.append({"role": "assistant", "content": answer.text})
        last = answer
    return 0 if last and fidelity(last) >= 0.9 else 1


async def cmd_select(args: argparse.Namespace) -> int:
    answer, hits = await ask_once(
        UUID(args.notebook),
        args.q,
        selection=args.selection,
        top_k=args.top_k,
    )
    # Soft signal: at least one cited chunk should overlap the selection's source.
    sel_words = {w.lower() for w in args.selection.split() if len(w) > 3}
    overlap = sum(
        1
        for c in answer.citations
        if any(w in hits[c.search_result_index].text.lower() for w in sel_words)
    )
    print(f"selection-overlap citations: {overlap}/{len(answer.citations)}")
    _print_answer(answer)
    return 0


async def cmd_stability(args: argparse.Namespace) -> int:
    candidates_runs: list[list[str]] = []
    for _ in range(args.runs):
        hits = await hybrid_retrieve(UUID(args.notebook), args.q, k=args.top_k)
        candidates_runs.append([str(h.chunk_id) for h in hits])

    baseline = candidates_runs[0]
    diffs = [
        sum(1 for a, b in zip(baseline, run, strict=False) if a != b) for run in candidates_runs
    ]
    print(f"runs={args.runs} top_k={args.top_k} order_diffs={diffs}")
    return 0 if all(d == 0 for d in diffs) else 1


async def cmd_bulk(args: argparse.Namespace) -> int:
    """Run every {"q": "..."} (and optional "selection") in the file, emit JSONL."""
    path = Path(args.file)
    questions = [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]

    fidelities: list[float] = []
    started = datetime.now(UTC).isoformat()
    for i, q in enumerate(questions):
        answer, _ = await ask_once(
            UUID(args.notebook),
            q["q"],
            selection=q.get("selection"),
            top_k=args.top_k,
        )
        f = fidelity(answer)
        fidelities.append(f)
        _emit(
            {
                "i": i,
                "q": q["q"],
                "answer": answer.text,
                "n_citations": len(answer.citations),
                "fidelity": f,
                "ungrounded": [c.cited_text for c in answer.citations if not c.roundtrip_ok],
            }
        )

    avg = sum(fidelities) / len(fidelities) if fidelities else 0.0
    summary = {
        "_summary": True,
        "started": started,
        "finished": datetime.now(UTC).isoformat(),
        "n": len(questions),
        "avg_fidelity": avg,
        "passed": avg >= 0.9,
    }
    _emit(summary)
    return 0 if avg >= 0.9 else 1


# ---- helpers ---------------------------------------------------------------


def _present(s: str | None) -> str:
    return "set" if s else "MISSING"


# ---- CLI -------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="m3",
        description="M3 prototype: end-to-end Citations API roundtrip.",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("health", help="Check providers + DB are reachable")

    ask_p = sub.add_parser("ask", help="One grounded question")
    _add_nb(ask_p)
    ask_p.add_argument("--q", required=True)
    _add_top_k(ask_p)

    chat_p = sub.add_parser("chat", help="Multi-turn follow-up")
    _add_nb(chat_p)
    chat_p.add_argument("--turns", nargs="+", required=True, help="space-separated quoted turns")
    _add_top_k(chat_p)

    sel_p = sub.add_parser("select", help="Question with user-selected text as context")
    _add_nb(sel_p)
    sel_p.add_argument("--selection", required=True)
    sel_p.add_argument("--q", required=True)
    _add_top_k(sel_p)

    stab_p = sub.add_parser("stability", help="Same query N times — top hits stable?")
    _add_nb(stab_p)
    stab_p.add_argument("--q", required=True)
    stab_p.add_argument("--runs", type=int, default=3)
    _add_top_k(stab_p)

    bulk_p = sub.add_parser("bulk", help="Run a JSONL of questions and grade")
    _add_nb(bulk_p)
    bulk_p.add_argument("--file", required=True, help="Path to JSONL of {q, selection?}")
    _add_top_k(bulk_p)

    return p


def _add_nb(p: argparse.ArgumentParser) -> None:
    p.add_argument("--notebook", required=True, help="Notebook UUID")


def _add_top_k(p: argparse.ArgumentParser) -> None:
    p.add_argument("--top-k", type=int, default=8, dest="top_k")


_DISPATCH = {
    "health": cmd_health,
    "ask": cmd_ask,
    "chat": cmd_chat,
    "select": cmd_select,
    "stability": cmd_stability,
    "bulk": cmd_bulk,
}


async def _main_async(argv: list[str] | None) -> int:
    args = _build_parser().parse_args(argv)
    configure_tracing()
    return await _DISPATCH[args.cmd](args)


def main(argv: list[str] | None = None) -> int:
    import asyncio as _asyncio
    import sys as _sys

    if _sys.platform == "win32":
        _asyncio.set_event_loop_policy(_asyncio.WindowsSelectorEventLoopPolicy())
    return asyncio.run(_main_async(argv))


if __name__ == "__main__":
    raise SystemExit(main())
