"""Notebook-level summary artifact (post-v1 Option A).

One structured Claude/Gemini call over the notebook's sources. The result is
persisted on `notebook.settings["summary"]` and re-generated on demand from
the UI — no separate `artifact` table for this single artifact; that lands in
PLAN.md M10 if more artifact types are added.

Reuses the same pattern as `pynote_core.outliner`:
    1. Pydantic schema constrains shape
    2. `with_structured_output(schema)` does the heavy lifting
    3. Transient model failures are retried; persistent ones raised

Input budgeting: the char cap is split across sources by waterfill (short
sources keep what they need, the leftover goes to longer ones) so a large
first document can't crowd every other source out of the summary.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from langchain_core.messages import HumanMessage
from pydantic import BaseModel, Field, ValidationError

from pynote_core.llm import get_heavy_model

if TYPE_CHECKING:
    from collections.abc import Sequence

log = logging.getLogger("pynote_core.summarizer")

# Cap total input around ~30k chars (~7-8k tokens). Summary quality benefits
# from longer context than the per-source outline; we give the heavier model
# more room. Cheap model would clip earlier.
MAX_INPUT_CHARS = 30_000

# Sleeps between retries of the model call — transient proxy/rate-limit errors
# (the cause of user-facing 502s) usually clear within seconds. len+1 attempts.
RETRY_DELAYS_S: tuple[float, ...] = (2.0, 5.0)


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
    "documents from a research notebook and produce a structured summary that "
    "covers all of the documents, not just the first. Be specific — name "
    "things, quote phrasing, give concrete claims. Avoid throat-clearing like "
    "'this notebook discusses…'."
)


def _allocate_budget(lengths: Sequence[int], budget: int) -> list[int]:
    """Split `budget` chars across docs by waterfill.

    Docs are visited shortest-first; each gets an equal share of what's left,
    and anything a short doc doesn't use flows to the longer ones. Every doc
    with text is guaranteed a non-zero slice (as long as budget >= n docs).
    """
    alloc = [0] * len(lengths)
    order = sorted(range(len(lengths)), key=lambda i: lengths[i])
    remaining = budget
    for pos, i in enumerate(order):
        docs_left = len(order) - pos
        share = remaining // docs_left
        alloc[i] = min(lengths[i], share)
        remaining -= alloc[i]
    return alloc


def _render_docs(docs: Sequence[tuple[str | None, str]]) -> str:
    """Budget + label each source so the model sees all of them by name."""
    lengths = [len(text) for _, text in docs]
    allocs = _allocate_budget(lengths, MAX_INPUT_CHARS)
    sections = [
        f"## {title or 'Untitled source'}\n{text[:take]}"
        for (title, text), take in zip(docs, allocs, strict=True)
    ]
    return "\n\n".join(sections)


def _coerce_summary(payload: object) -> NotebookSummary | None:
    """Validate model output into `NotebookSummary`, tolerating one wrapper level.

    Models sometimes emit the object nested under a single key — e.g.
    `{"summary": {"headline": ...}}` — despite the tool schema. If top-level
    validation fails and the dict has exactly one dict value, try that inner
    dict before giving up.
    """
    if isinstance(payload, NotebookSummary):
        return payload
    if not isinstance(payload, dict):
        return None
    try:
        return NotebookSummary.model_validate(payload)
    except ValidationError:
        pass
    if len(payload) == 1:
        (inner,) = payload.values()
        if isinstance(inner, dict):
            try:
                return NotebookSummary.model_validate(inner)
            except ValidationError:
                return None
    return None


def _parse_structured_output(out: object) -> NotebookSummary:
    """Extract a summary from an `include_raw=True` structured-output payload.

    Checks, in order: the pre-parsed object, then the raw tool-call args
    (where a wrapped-but-valid payload lands when LangChain's parse failed).
    """
    if isinstance(out, dict):
        summary = _coerce_summary(out.get("parsed"))
        if summary is not None:
            return summary
        raw = out.get("raw")
        for call in getattr(raw, "tool_calls", None) or []:
            summary = _coerce_summary(call.get("args"))
            if summary is not None:
                return summary
        error = out.get("parsing_error")
        if isinstance(error, Exception):
            raise error
    summary = _coerce_summary(out)
    if summary is not None:
        return summary
    raise TypeError(f"Expected NotebookSummary, got {type(out).__name__}")


async def generate_notebook_summary(
    docs: Sequence[tuple[str | None, str]],
) -> NotebookSummary:
    """Summarize `[(source_title, source_text), ...]` into a typed summary.

    The char budget is split across sources (waterfill) so every document
    contributes. The model call is retried on transient failures; raises on
    empty input or persistent model failure.
    """
    cleaned = [(title, text.strip()) for title, text in docs if (text or "").strip()]
    if not cleaned:
        raise ValueError("Cannot summarize an empty notebook.")
    rendered = _render_docs(cleaned)

    model = get_heavy_model()
    # include_raw so a schema mismatch surfaces as data we can repair
    # (see _parse_structured_output) instead of an exception mid-parse.
    structured = model.with_structured_output(NotebookSummary, include_raw=True)
    message = HumanMessage(content=f"{_SYSTEM}\n\nDOCUMENTS:\n{rendered}\n\nReturn the summary.")

    last_error: Exception | None = None
    for attempt in range(len(RETRY_DELAYS_S) + 1):
        if attempt > 0:
            delay = RETRY_DELAYS_S[attempt - 1]
            log.warning(
                "summary generation attempt %d failed (%s); retrying in %.0fs",
                attempt,
                type(last_error).__name__,
                delay,
            )
            await asyncio.sleep(delay)
        try:
            return _parse_structured_output(await structured.ainvoke([message]))
        except Exception as e:  # proxy/rate-limit error types vary by provider
            last_error = e

    assert last_error is not None
    raise last_error
