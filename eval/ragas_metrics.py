"""Optional Ragas integration.

Ragas is a heavy dependency (langchain + datasets + numpy + pyarrow). We keep
it as an *optional* extra: callers try to import; if it's missing, the
eval falls back to the lite metrics only.

Install with:
    uv pip install --group eval

Designed to run with the free-tier `get_cheap_model()` (Gemini Flash) as the
judge — Ragas calls the judge for each metric per row.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence


@dataclass(frozen=True, slots=True)
class RagasScores:
    faithfulness: float | None
    answer_relevancy: float | None
    context_precision: float | None
    context_recall: float | None


def is_available() -> bool:
    """True if the `ragas` package is importable."""
    try:
        import ragas  # noqa: F401

        return True
    except ImportError:
        return False


async def score_with_ragas(
    rows: Sequence[dict],
) -> list[RagasScores]:
    """Run Ragas faithfulness + answer_relevancy + context_{precision,recall}.

    Each row must carry: `question, contexts (list[str]), answer, reference?`.
    `context_precision`/`context_recall` require `reference`; absent rows
    return `None` for those metrics.

    Uses the cheap LLM as judge (Gemini Flash on free tier).
    """
    from ragas import EvaluationDataset, evaluate
    from ragas.llms import LangchainLLMWrapper
    from ragas.metrics import answer_relevancy, faithfulness

    from pynote_core.llm import get_cheap_model

    judge = LangchainLLMWrapper(get_cheap_model())

    samples = [
        {
            "user_input": str(r["question"]),
            "retrieved_contexts": list(r.get("contexts") or []),
            "response": str(r.get("answer") or ""),
            **({"reference": str(r["reference"])} if r.get("reference") else {}),
        }
        for r in rows
    ]
    if not samples:
        return []

    metrics = [faithfulness, answer_relevancy]
    has_ref = all("reference" in s for s in samples)
    if has_ref:
        from ragas.metrics import context_precision, context_recall

        metrics.extend([context_precision, context_recall])

    dataset = EvaluationDataset.from_list(samples)
    result = evaluate(dataset, metrics=metrics, llm=judge)
    df = result.to_pandas()

    out: list[RagasScores] = []
    for i in range(len(df)):
        row = df.iloc[i]
        out.append(
            RagasScores(
                faithfulness=_safe_float(row.get("faithfulness")),
                answer_relevancy=_safe_float(row.get("answer_relevancy")),
                context_precision=_safe_float(row.get("context_precision")) if has_ref else None,
                context_recall=_safe_float(row.get("context_recall")) if has_ref else None,
            )
        )
    return out


def _safe_float(v: object) -> float | None:
    if v is None:
        return None
    try:
        f = float(v)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    # Ragas marks failed rows as NaN.
    return None if f != f else f
