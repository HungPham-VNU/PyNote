"""Per-source outline generator (M6).

Runs after `embed_source` and writes onto `source.meta`:
    {
      "abstract": "2-3 sentence summary",
      "key_entities": [...],
      "suggested_questions": ["...", "...", "..."]
    }

Used by the notebook home page to surface "Try asking…" chips.

Cheap-model only — Gemini 2.0 Flash on free tier, Haiku otherwise. The whole
call costs roughly one query against ~3-4k input tokens, well under any
free-tier daily budget.
"""

from __future__ import annotations

from langchain_core.messages import HumanMessage
from pydantic import BaseModel, Field

from pynote_core.llm import get_cheap_model

# Cap input to ~15k chars (~4k tokens). Longer inputs make Gemini/Haiku slow
# without measurably improving the outline. Chunkers feed in document order
# so the prefix is representative.
MAX_INPUT_CHARS = 15_000


class SourceOutline(BaseModel):
    """Generated metadata persisted on `source.meta`."""

    abstract: str = Field(
        description="A 2-3 sentence summary of the document. Plain prose, no bullet points.",
    )
    key_entities: list[str] = Field(
        description=(
            "5-10 main entities, topics, or concepts named in the document. "
            "Short noun phrases, no full sentences."
        ),
        min_length=3,
        max_length=12,
    )
    suggested_questions: list[str] = Field(
        description=(
            "3-5 specific, answerable questions a reader might ask about this "
            "document. Each question must be self-contained and grounded in the text."
        ),
        min_length=3,
        max_length=5,
    )


_SYSTEM = (
    "You are an outline generator. Read the document and produce a brief "
    "outline. The suggested questions you write will be shown to users as "
    "clickable chips, so each must be specific, answerable from the document, "
    "and self-contained."
)


async def generate_outline(text: str) -> SourceOutline:
    """Best-effort outline generation. Raises on model/parsing failure."""
    snippet = (text or "").strip()
    if not snippet:
        raise ValueError("Cannot outline empty text.")
    snippet = snippet[:MAX_INPUT_CHARS]

    model = get_cheap_model()
    structured = model.with_structured_output(SourceOutline)
    result = await structured.ainvoke(
        [
            HumanMessage(content=f"{_SYSTEM}\n\nDOCUMENT:\n{snippet}\n\nReturn the outline."),
        ],
    )
    # `with_structured_output` returns an instance of the schema class.
    if not isinstance(result, SourceOutline):
        raise TypeError(f"Expected SourceOutline, got {type(result).__name__}")
    return result
