"""Outliner tests — schema validation + input guards.

The actual model call is skipped without an API key (would cost cents per run
and need network), but the schema and the empty-input guard are pure-Python.
"""

import os

import pytest
from pydantic import ValidationError

from pynote_core.outliner import MAX_INPUT_CHARS, SourceOutline, generate_outline


def test_schema_requires_three_to_five_questions() -> None:
    SourceOutline(
        abstract="x. y.",
        key_entities=["a", "b", "c"],
        suggested_questions=["q1?", "q2?", "q3?"],
    )
    with pytest.raises(ValidationError):
        SourceOutline(
            abstract="x.",
            key_entities=["a", "b", "c"],
            suggested_questions=["only one?"],
        )
    with pytest.raises(ValidationError):
        SourceOutline(
            abstract="x.",
            key_entities=["a", "b", "c"],
            suggested_questions=["q?"] * 6,
        )


def test_schema_caps_entities_count() -> None:
    SourceOutline(
        abstract="x.",
        key_entities=["e"] * 12,
        suggested_questions=["q?"] * 3,
    )
    with pytest.raises(ValidationError):
        SourceOutline(
            abstract="x.",
            key_entities=["e"] * 13,
            suggested_questions=["q?"] * 3,
        )


@pytest.mark.asyncio
async def test_generate_outline_rejects_empty_input() -> None:
    with pytest.raises(ValueError, match="empty"):
        await generate_outline("")
    with pytest.raises(ValueError, match="empty"):
        await generate_outline("   \n\t  ")


def test_max_input_chars_is_reasonable() -> None:
    # A safety check: someone bumping this above ~50k would blow free-tier
    # daily budgets quickly. 15k is comfortable for English; flag bigger.
    assert MAX_INPUT_CHARS <= 30_000


@pytest.mark.skipif(
    not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("GOOGLE_API_KEY")),
    reason="Set ANTHROPIC_API_KEY or GOOGLE_API_KEY for the live smoke test.",
)
@pytest.mark.asyncio
async def test_generate_outline_smoke() -> None:
    text = (
        "PyNote is a research assistant that lets users upload PDFs and ask "
        "grounded questions. Every answer cites the exact source span. The "
        "architecture uses Postgres with pgvector for retrieval and Claude "
        "for generation. Citations are produced by Anthropic's Citations API."
    )
    outline = await generate_outline(text)
    assert len(outline.suggested_questions) >= 3
    assert outline.abstract
