"""Mind-map generation tests (M12).

The two-pass extraction itself calls the heavy LLM, so we stub the model and
assert the deterministic scaffolding around it: block budgeting, citation
roundtrip, and — critically — that edges referencing unknown node ids are
dropped so the rendered graph can never dangle.
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest

from pynote_core import mindmap
from pynote_core.mindmap import (
    MAX_INPUT_CHARS,
    EdgeExtractionResult,
    NodeExtractionResult,
    _build_blocks,
    _CitationDraft,
    _EdgeDraft,
    _NodeDraft,
    _resolve_citation,
    generate_mind_map,
)
from pynote_core.models import SourcePart


def _part(text: str, ordinal: int = 0, page: int | None = 1) -> SourcePart:
    return SourcePart(id=uuid4(), source_id=uuid4(), ordinal=ordinal, page=page, text=text)


# ---- block construction ----------------------------------------------------


def test_blocks_skip_empty_parts_and_carry_identity() -> None:
    p = _part("Photosynthesis converts light into energy.")
    [b] = _build_blocks([(p, "doc-a"), (_part("   ", 1), "doc-b")])
    assert b.source_part_id == p.id
    assert b.source_title == "doc-a"
    assert b.page == 1


def test_blocks_respect_total_char_budget() -> None:
    big = _part("x" * (MAX_INPUT_CHARS + 5_000))
    [b] = _build_blocks([(big, "doc")])
    assert len(b.text) == MAX_INPUT_CHARS


# ---- citation resolution ---------------------------------------------------


def test_resolve_citation_roundtrips_present_quote() -> None:
    [b] = _build_blocks([(_part("alpha beta gamma"), "doc")])
    c = _resolve_citation(_CitationDraft(block_index=0, quote="beta"), [b])
    assert c is not None
    assert c.roundtrip_ok is True
    assert c.page == 1


def test_resolve_citation_flags_absent_quote() -> None:
    [b] = _build_blocks([(_part("alpha beta gamma"), "doc")])
    c = _resolve_citation(_CitationDraft(block_index=0, quote="delta"), [b])
    assert c is not None
    assert c.roundtrip_ok is False


def test_resolve_citation_rejects_out_of_range_block() -> None:
    [b] = _build_blocks([(_part("alpha"), "doc")])
    assert _resolve_citation(_CitationDraft(block_index=9, quote="alpha"), [b]) is None


# ---- two-pass generation (stubbed model) -----------------------------------


class _FakeStructured:
    def __init__(self, result: Any) -> None:
        self._result = result

    async def ainvoke(self, _messages: Any) -> Any:
        return self._result


class _FakeModel:
    """Returns the node result on the first `with_structured_output`, the edge
    result on the second — matching `generate_mind_map`'s two-pass order.
    """

    def __init__(self, node_result: Any, edge_result: Any) -> None:
        self._results = [node_result, edge_result]

    def with_structured_output(self, _schema: Any) -> _FakeStructured:
        return _FakeStructured(self._results.pop(0))


@pytest.mark.asyncio
async def test_generate_drops_edges_with_unknown_node_ids(monkeypatch: Any) -> None:
    parts = [(_part("gradient descent minimizes the loss function"), "ml")]

    nodes = NodeExtractionResult(
        nodes=[
            _NodeDraft(
                id="gradient_descent",
                label="Gradient Descent",
                kind="concept",
                citations=[_CitationDraft(block_index=0, quote="gradient descent")],
            ),
            _NodeDraft(
                id="loss",
                label="Loss Function",
                kind="concept",
                citations=[_CitationDraft(block_index=0, quote="loss function")],
            ),
        ]
    )
    edges = EdgeExtractionResult(
        edges=[
            _EdgeDraft(
                **{"from": "gradient_descent", "to": "loss"},
                label="minimizes",
                citations=[_CitationDraft(block_index=0, quote="minimizes the loss")],
            ),
            # References a node id that does not exist — must be dropped.
            _EdgeDraft(
                **{"from": "gradient_descent", "to": "ghost_node"},
                label="relates to",
                citations=[_CitationDraft(block_index=0, quote="gradient descent")],
            ),
        ]
    )
    monkeypatch.setattr(mindmap, "get_heavy_model", lambda: _FakeModel(nodes, edges))

    result = await generate_mind_map(parts)

    assert {n.id for n in result.nodes} == {"gradient_descent", "loss"}
    assert len(result.edges) == 1
    assert (result.edges[0].from_id, result.edges[0].to_id) == ("gradient_descent", "loss")
    assert result.edges[0].citations[0].roundtrip_ok is True


@pytest.mark.asyncio
async def test_generate_rejects_empty_notebook() -> None:
    with pytest.raises(ValueError, match="no text"):
        await generate_mind_map([(_part("   "), "doc")])


@pytest.mark.asyncio
async def test_generate_trims_model_overshoot_instead_of_failing(monkeypatch: Any) -> None:
    """The MAX_NODES/MAX_EDGES caps are prompt guidance the model may exceed
    (observed: 116 nodes against a cap of 100) — overshoot must be trimmed,
    not blow up the whole generation with a ValidationError.
    """
    parts = [(_part("alpha beta gamma"), "doc")]
    cite = [_CitationDraft(block_index=0, quote="alpha")]

    nodes = NodeExtractionResult(
        nodes=[
            _NodeDraft(id=f"n{i}", label=f"Node {i}", kind="concept", citations=cite)
            for i in range(mindmap.MAX_NODES + 16)
        ]
    )
    edges = EdgeExtractionResult(
        edges=[_EdgeDraft(**{"from": "n0", "to": "n1"}, label="relates to", citations=cite * 7)]
    )
    monkeypatch.setattr(mindmap, "get_heavy_model", lambda: _FakeModel(nodes, edges))

    result = await generate_mind_map(parts)

    assert len(result.nodes) == mindmap.MAX_NODES
    # Citations beyond the per-item cap are dropped, not fatal.
    assert len(result.edges[0].citations) == mindmap.MAX_CITATIONS_PER_ITEM
