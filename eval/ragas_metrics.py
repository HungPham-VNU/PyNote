"""Optional Ragas integration.

Ragas is a heavy dependency (langchain + datasets + numpy + pyarrow). We keep
it as an *optional* extra: callers try to import; if it's missing, the
eval falls back to the lite metrics only.

Install with:
    uv sync --all-packages --group eval

Free-tier setup (no OpenAI key required):
- Judge LLM:    Gemini Flash via `get_cheap_model()` — one call per metric per row.
- Embeddings:   local BGE-small via `_BGEEmbeddingsForRagas` — used by
                `answer_relevancy` (cosine sim between Q and reconstructed-Q).
                Without this adapter Ragas falls back to OpenAIEmbeddings.
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


class _BGEEmbeddingsForRagas:
    """LangChain `Embeddings`-compatible adapter over our local fastembed BGE.

    Ragas' `answer_relevancy` metric needs an embedding model (cosine sim
    between the original question and a question generated from the answer).
    Without one supplied, ragas falls back to OpenAIEmbeddings — which fails
    if OPENAI_API_KEY isn't set. We point it at the same local model the rest
    of the app uses, keeping the eval free-tier-friendly.
    """

    def __init__(self) -> None:
        from fastembed import TextEmbedding

        from pynote_core.settings import get_settings

        settings = get_settings()
        self._model = TextEmbedding(model_name=settings.embedding_model)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [list(map(float, v)) for v in self._model.embed(texts)]

    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents([text])[0]

    async def aembed_documents(self, texts: list[str]) -> list[list[float]]:
        import asyncio

        return await asyncio.to_thread(self.embed_documents, texts)

    async def aembed_query(self, text: str) -> list[float]:
        import asyncio

        return await asyncio.to_thread(self.embed_query, text)


async def score_with_ragas(
    rows: Sequence[dict],
) -> list[RagasScores]:
    """Run Ragas faithfulness + answer_relevancy + context_{precision,recall}.

    Each row must carry: `question, contexts (list[str]), answer, reference?`.
    `context_precision`/`context_recall` require `reference`; absent rows
    return `None` for those metrics.

    Uses the cheap LLM as judge (Gemini Flash on free tier) and the local
    BGE-small embedder for similarity-based metrics — no OpenAI key required.
    """
    from ragas import EvaluationDataset, evaluate
    from ragas.embeddings import LangchainEmbeddingsWrapper
    from ragas.llms import LangchainLLMWrapper
    from ragas.metrics import answer_relevancy, faithfulness

    from pynote_core.llm import get_cheap_model

    judge = LangchainLLMWrapper(get_cheap_model())
    embeddings = LangchainEmbeddingsWrapper(_BGEEmbeddingsForRagas())

    samples = [
        {
            # eval/run.py rows carry the question under "q"; accept both.
            "user_input": str(r.get("question") or r.get("q") or ""),
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
    # Free-tier judges throttle hard (flash-lite: 15 RPM). Few workers + a
    # generous per-job timeout beat the defaults, which burst then TimeoutError.
    from ragas import RunConfig

    run_config = RunConfig(timeout=300, max_workers=4)
    result = evaluate(
        dataset, metrics=metrics, llm=judge, embeddings=embeddings, run_config=run_config
    )
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
