"""Summarizer schema validation + empty-input guard."""

import pytest
from pydantic import ValidationError

from pynote_core.summarizer import MAX_INPUT_CHARS, NotebookSummary, generate_notebook_summary


def test_schema_enforces_key_point_bounds() -> None:
    NotebookSummary(
        headline="x",
        key_points=["a", "b", "c"],
        detailed_summary="paragraph.",
    )
    with pytest.raises(ValidationError):
        NotebookSummary(
            headline="x",
            key_points=["a", "b"],
            detailed_summary="paragraph.",
        )
    with pytest.raises(ValidationError):
        NotebookSummary(
            headline="x",
            key_points=["a", "b", "c", "d", "e", "f", "g", "h"],
            detailed_summary="paragraph.",
        )


def test_schema_caps_headline_length() -> None:
    with pytest.raises(ValidationError):
        NotebookSummary(
            headline="x" * 301,
            key_points=["a", "b", "c"],
            detailed_summary=".",
        )


@pytest.mark.asyncio
async def test_generate_summary_rejects_empty_input() -> None:
    with pytest.raises(ValueError, match="empty"):
        await generate_notebook_summary("")
    with pytest.raises(ValueError, match="empty"):
        await generate_notebook_summary("   \n\t  ")


def test_input_cap_is_reasonable() -> None:
    # Bumping MAX_INPUT_CHARS above ~60k would burn free-tier daily budgets fast.
    assert MAX_INPUT_CHARS <= 60_000
