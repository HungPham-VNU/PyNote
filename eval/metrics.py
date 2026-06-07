"""M7 metrics — pure functions over (question, contexts, answer, citations).

Citation-grounding is the headline gate (the same metric we computed in M3's
`fidelity()`, lifted out and named more explicitly). The lightweight `*_lite`
metrics are heuristic substitutes that run without an LLM judge — useful for
fast feedback loops. The real Ragas metrics land in `eval.ragas_metrics`,
which is imported lazily so the base eval doesn't require the heavyweight
optional dep.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

    from pynote_core.citations import ParsedAnswer


# ---- citation grounding ----------------------------------------------------


def citation_grounding(answer: ParsedAnswer) -> float:
    """Fraction of citations whose char-offset roundtrip succeeds.

    This is the ship-gate metric — it directly measures whether Anthropic's
    Citations API offsets resolve to the exact substring of the chunk we
    retrieved. Returns 1.0 when there are no citations (no claims = no lies).
    """
    if not answer.citations:
        return 1.0
    ok = sum(1 for c in answer.citations if c.roundtrip_ok)
    return ok / len(answer.citations)


# ---- lightweight (no-LLM) faithfulness / answer relevancy ------------------


_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _tokens(text: str) -> set[str]:
    return set(_TOKEN_RE.findall(text.lower()))


@dataclass(frozen=True, slots=True)
class LiteScores:
    faithfulness: float  # fraction of answer tokens that appear in contexts
    answer_relevancy: float  # token overlap (answer, question)
    grounding_overlap: float  # fraction of citations whose cited_text appears in any context


def lite_scores(
    question: str,
    contexts: Sequence[str],
    answer_text: str,
    cited_texts: Sequence[str],
) -> LiteScores:
    """Cheap proxies for the heavy Ragas metrics — no LLM call.

    They are crude (word-overlap) and should not be the ship gate alone, but
    they're useful when you want fast feedback (e.g. inside a tuning loop on
    `top_k`) without burning model tokens.
    """
    q_tok = _tokens(question)
    a_tok = _tokens(answer_text)
    ctx_tok: set[str] = set()
    for c in contexts:
        ctx_tok |= _tokens(c)

    faithfulness = (len(a_tok & ctx_tok) / len(a_tok)) if a_tok else 1.0
    relevancy = (len(a_tok & q_tok) / len(q_tok)) if q_tok else 0.0

    if cited_texts:
        grounded = sum(
            1 for ct in cited_texts if any(ct.strip() and ct.strip() in c for c in contexts)
        )
        overlap = grounded / len(cited_texts)
    else:
        overlap = 1.0

    return LiteScores(
        faithfulness=faithfulness,
        answer_relevancy=relevancy,
        grounding_overlap=overlap,
    )


# ---- ship gate aggregator --------------------------------------------------


@dataclass(frozen=True, slots=True)
class GateResult:
    citation_grounding_avg: float
    faithfulness_lite_avg: float
    answer_relevancy_lite_avg: float
    n: int
    passed: bool


# v1 ship thresholds — tuned for "clean and simple" demo grading. Tighten
# when there's a real golden set and Ragas evidence to back it up.
CITATION_GROUNDING_GATE = 0.90
FAITHFULNESS_LITE_GATE = 0.60
ANSWER_RELEVANCY_LITE_GATE = 0.25


def aggregate(rows: Sequence[dict]) -> GateResult:
    """Compute the v1 ship gate over per-question rows.

    Each row must carry the float metric fields produced by `eval/run.py`.
    Missing fields are treated as 0 — explicitly catching the case where a
    question failed before metrics could be computed.
    """
    n = len(rows)
    if n == 0:
        return GateResult(0.0, 0.0, 0.0, 0, passed=False)
    cg = sum(float(r.get("citation_grounding", 0.0)) for r in rows) / n
    fl = sum(float(r.get("faithfulness_lite", 0.0)) for r in rows) / n
    ar = sum(float(r.get("answer_relevancy_lite", 0.0)) for r in rows) / n
    passed = (
        cg >= CITATION_GROUNDING_GATE
        and fl >= FAITHFULNESS_LITE_GATE
        and ar >= ANSWER_RELEVANCY_LITE_GATE
    )
    return GateResult(
        citation_grounding_avg=cg,
        faithfulness_lite_avg=fl,
        answer_relevancy_lite_avg=ar,
        n=n,
        passed=passed,
    )
