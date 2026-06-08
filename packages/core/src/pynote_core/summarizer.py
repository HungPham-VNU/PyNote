"""Notebook-level summary artifact (post-v1 Option A).

One structured Claude/Gemini call over the full notebook's joined text. The
result is persisted on `notebook.settings["summary"]` and re-generated on
demand from the UI — no separate `artifact` table for this single artifact;
that lands in PLAN.md M10 if more artifact types are added.

Reuses the same pattern as `pynote_core.outliner`:
    1. Pydantic schema constrains shape
    2. `with_structured_output(schema)` does the heavy lifting
    3. Best-effort — errors are raised; caller decides whether to retry
"""

from __future__ import annotations

from langchain_core.messages import HumanMessage
from pydantic import BaseModel, Field

from pynote_core.llm import get_heavy_model

# Cap input around ~30k chars (~7-8k tokens). Summary quality benefits from
# longer context than the per-source outline; we give the heavier model more
# room. Cheap model would clip earlier.
MAX_INPUT_CHARS = 30_000


class NotebookSummary(BaseModel):
    """Generated notebook summary stored on `notebook.settings['summary']`."""

    headline: str = Field(
        description=(
            "A single-sentence high-level statement of what the notebook is about. "
            "Should read like a thesis. No bullet points."
        ),
        max_length=300,
    )
    key_points: list[str] = Field(
        description=(
            "3-7 concise bullet points covering the most important findings, "
            "claims, or themes across all sources. Each is a complete sentence."
        ),
        min_length=3,
        max_length=7,
    )
    detailed_summary: str = Field(
        description=(
            "A 2-4 paragraph narrative summary connecting the key points. "
            "Plain prose, ~150-300 words. Grounded in the sources."
        ),
    )


_SYSTEM = (
    "You are an editorial summarizer. Read the combined text of one or more "
    "documents from a research notebook and produce a structured summary. "
    "Be specific — name things, quote phrasing, give concrete claims. Avoid "
    "throat-clearing like 'this notebook discusses…'."
)


async def generate_notebook_summary(joined_text: str) -> NotebookSummary:
    """One model call → typed summary. Raises on empty input or model failure."""
    text = (joined_text or "").strip()
    if not text:
        raise ValueError("Cannot summarize an empty notebook.")
    text = text[:MAX_INPUT_CHARS]

    model = get_heavy_model()
    structured = model.with_structured_output(NotebookSummary)
    result = await structured.ainvoke(
        [HumanMessage(content=f"{_SYSTEM}\n\nDOCUMENTS:\n{text}\n\nReturn the summary.")],
    )
    if not isinstance(result, NotebookSummary):
        raise TypeError(f"Expected NotebookSummary, got {type(result).__name__}")
    return result
