"""Summarizer schema validation, budget allocation, retry, and input guards."""

from typing import Any

import pytest
from pydantic import ValidationError

from pynote_core import summarizer
from pynote_core.summarizer import (
    MAX_INPUT_CHARS,
    NotebookSummary,
    _allocate_budget,
    _render_docs,
    generate_notebook_summary,
)


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
        await generate_notebook_summary([])
    with pytest.raises(ValueError, match="empty"):
        await generate_notebook_summary([("doc", ""), ("doc2", "   \n\t  ")])


def test_input_cap_is_reasonable() -> None:
    # Bumping MAX_INPUT_CHARS above ~60k would burn free-tier daily budgets fast.
    assert MAX_INPUT_CHARS <= 60_000


# ---- budget allocation -------------------------------------------------------


def test_allocate_splits_budget_equally_when_all_docs_are_long() -> None:
    assert _allocate_budget([1000, 1000], 300) == [150, 150]


def test_allocate_redistributes_unused_share_to_long_docs() -> None:
    # The 10-char doc keeps 10; its unused share flows to the big doc.
    assert _allocate_budget([10, 1000], 100) == [10, 90]


def test_allocate_never_exceeds_budget() -> None:
    alloc = _allocate_budget([50_000, 40_000, 30], MAX_INPUT_CHARS)
    assert sum(alloc) <= MAX_INPUT_CHARS
    assert all(a > 0 for a in alloc)


def test_render_includes_every_source_by_title() -> None:
    # A first doc bigger than the whole budget must not crowd out the second.
    rendered = _render_docs(
        [("big-doc", "x" * (MAX_INPUT_CHARS * 2)), ("small-doc", "unique-marker")]
    )
    assert "## big-doc" in rendered
    assert "## small-doc" in rendered
    assert "unique-marker" in rendered
    assert len(rendered) <= MAX_INPUT_CHARS + 200  # headers are overhead, not budget


# ---- retry on transient model failure ----------------------------------------


class _FlakyStructured:
    """Fails `failures` times, then returns a valid summary."""

    def __init__(self, failures: int) -> None:
        self.failures = failures
        self.calls = 0

    async def ainvoke(self, _messages: Any) -> NotebookSummary:
        self.calls += 1
        if self.calls <= self.failures:
            raise ConnectionError("upstream hiccup")
        return NotebookSummary(
            headline="h",
            key_points=["a", "b", "c"],
            detailed_summary="d",
        )


class _FakeModel:
    def __init__(self, structured: Any) -> None:
        self._structured = structured

    def with_structured_output(self, _schema: Any, **_kwargs: Any) -> Any:
        return self._structured


@pytest.mark.asyncio
async def test_generate_retries_transient_failures(monkeypatch: Any) -> None:
    flaky = _FlakyStructured(failures=2)
    monkeypatch.setattr(summarizer, "get_heavy_model", lambda: _FakeModel(flaky))
    monkeypatch.setattr(summarizer, "RETRY_DELAYS_S", (0.0, 0.0))

    result = await generate_notebook_summary([("doc", "some text")])
    assert result.headline == "h"
    assert flaky.calls == 3  # 2 failures + 1 success


@pytest.mark.asyncio
async def test_generate_raises_after_retries_exhausted(monkeypatch: Any) -> None:
    flaky = _FlakyStructured(failures=99)
    monkeypatch.setattr(summarizer, "get_heavy_model", lambda: _FakeModel(flaky))
    monkeypatch.setattr(summarizer, "RETRY_DELAYS_S", (0.0,))

    with pytest.raises(ConnectionError, match="upstream hiccup"):
        await generate_notebook_summary([("doc", "some text")])
    assert flaky.calls == 2  # 1 + 1 retry, then gave up


# ---- schema-wrapping repair ----------------------------------------------------


class _RawToolCallMessage:
    """Stands in for an AIMessage whose tool call carried a wrapped payload."""

    def __init__(self, args: dict[str, Any]) -> None:
        self.tool_calls = [{"name": "NotebookSummary", "args": args}]


class _WrappedStructured:
    """Simulates a model that nests the object under a 'summary' key, which
    fails LangChain's parse (parsed=None) but is repairable from the raw args.
    """

    async def ainvoke(self, _messages: Any) -> dict[str, Any]:
        wrapped = {
            "summary": {
                "headline": "h",
                "key_points": ["a", "b", "c"],
                "detailed_summary": "d",
            }
        }
        return {
            "raw": _RawToolCallMessage(wrapped),
            "parsed": None,
            "parsing_error": ValueError("3 validation errors for NotebookSummary"),
        }


@pytest.mark.asyncio
async def test_generate_repairs_wrapped_model_output(monkeypatch: Any) -> None:
    monkeypatch.setattr(summarizer, "get_heavy_model", lambda: _FakeModel(_WrappedStructured()))
    monkeypatch.setattr(summarizer, "RETRY_DELAYS_S", ())

    result = await generate_notebook_summary([("doc", "some text")])
    assert result.headline == "h"
    assert result.key_points == ["a", "b", "c"]
