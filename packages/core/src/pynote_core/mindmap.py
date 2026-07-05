"""Notebook mind-map artifact (M12).

Two-pass structured generation over a notebook's sources:
    1. Node pass   — entities/concepts, each grounded in a cited quote.
    2. Edge pass   — relationships between the nodes from pass 1, each
       grounded in a cited quote.

Citations here are lighter-weight than the chat path's Anthropic
`search_result` citations (`pynote_core.citations`): the model cites a
block index + a verbatim quote, and we roundtrip-check the quote against
that block's known text ourselves. Same grounding contract, no Citations API.

Persisted on `notebook.settings["mind_map"]` — no new table, same pattern as
`pynote_core.summarizer`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID  # noqa: TC003 — needed at runtime for Pydantic field resolution

from langchain_core.messages import HumanMessage
from pydantic import BaseModel, Field

from pynote_core.llm import get_heavy_model

if TYPE_CHECKING:
    from pynote_core.models import SourcePart

# Cap total input. Mind maps span many sources, but the heavy model's context
# is the bottleneck cost-wise, not quality — 60k chars (~15k tokens) covers a
# 20-source academic notebook comfortably.
MAX_INPUT_CHARS = 60_000
MAX_NODES = 100
MAX_EDGES = 300


# ---- citation -----------------------------------------------------------


class _CitationDraft(BaseModel):
    """What the model emits: a pointer into the numbered block list."""

    block_index: int = Field(description="Index of the [B<i>] block the quote came from.")
    quote: str = Field(description="A short verbatim quote (<=200 chars) copied from that block.")


class MindMapCitation(BaseModel):
    """Resolved citation — block reference swapped for real source identity."""

    source_id: UUID
    source_part_id: UUID
    source_title: str | None
    page: int | None
    quote: str
    roundtrip_ok: bool


# ---- public shapes --------------------------------------------------------


class MindMapNode(BaseModel):
    id: str = Field(
        description="Short stable slug, e.g. 'gradient_descent'. Unique within the map."
    )
    label: str = Field(description="Human-readable name shown on the node.")
    kind: str = Field(description="One of: concept, entity, person, event, claim.")
    citations: list[MindMapCitation] = Field(default_factory=list)


class MindMapEdge(BaseModel):
    from_id: str = Field(alias="from")
    to_id: str = Field(alias="to")
    label: str = Field(
        description="Short verb phrase describing the relationship, e.g. 'depends on'."
    )
    citations: list[MindMapCitation] = Field(default_factory=list)

    model_config = {"populate_by_name": True}


class MindMap(BaseModel):
    nodes: list[MindMapNode]
    edges: list[MindMapEdge]


# ---- raw model output (block_index, not resolved citations) ---------------


class _NodeDraft(BaseModel):
    id: str = Field(description="Short stable slug, unique within the map.")
    label: str
    kind: str = Field(description="One of: concept, entity, person, event, claim.")
    citations: list[_CitationDraft] = Field(min_length=1, max_length=5)


class NodeExtractionResult(BaseModel):
    nodes: list[_NodeDraft] = Field(min_length=1, max_length=MAX_NODES)


class _EdgeDraft(BaseModel):
    from_id: str = Field(alias="from")
    to_id: str = Field(alias="to")
    label: str
    citations: list[_CitationDraft] = Field(min_length=1, max_length=5)

    model_config = {"populate_by_name": True}


class EdgeExtractionResult(BaseModel):
    edges: list[_EdgeDraft] = Field(max_length=MAX_EDGES)


# ---- block construction -----------------------------------------------------


class _Block:
    __slots__ = ("page", "source_id", "source_part_id", "source_title", "text")

    def __init__(
        self,
        source_id: UUID,
        source_part_id: UUID,
        source_title: str | None,
        page: int | None,
        text: str,
    ) -> None:
        self.source_id = source_id
        self.source_part_id = source_part_id
        self.source_title = source_title
        self.page = page
        self.text = text


def _build_blocks(parts: list[tuple[SourcePart, str | None]]) -> list[_Block]:
    """One block per non-empty SourcePart, capped to `MAX_INPUT_CHARS` total."""
    blocks: list[_Block] = []
    budget = MAX_INPUT_CHARS
    for part, source_title in parts:
        text = (part.text or "").strip()
        if not text or budget <= 0:
            continue
        text = text[:budget]
        budget -= len(text)
        blocks.append(_Block(part.source_id, part.id, source_title, part.page, text))
    return blocks


def _render_blocks(blocks: list[_Block]) -> str:
    chunks = []
    for i, b in enumerate(blocks):
        header = f"[B{i}] (source: {b.source_title or 'Untitled'}, page {b.page or '?'})"
        chunks.append(f"{header}\n{b.text}")
    return "\n\n".join(chunks)


def _resolve_citation(draft: _CitationDraft, blocks: list[_Block]) -> MindMapCitation | None:
    if not (0 <= draft.block_index < len(blocks)):
        return None
    block = blocks[draft.block_index]
    quote = draft.quote.strip()
    return MindMapCitation(
        source_id=block.source_id,
        source_part_id=block.source_part_id,
        source_title=block.source_title,
        page=block.page,
        quote=quote,
        roundtrip_ok=quote in block.text,
    )


def _resolve_citations(drafts: list[_CitationDraft], blocks: list[_Block]) -> list[MindMapCitation]:
    resolved = [_resolve_citation(d, blocks) for d in drafts]
    return [c for c in resolved if c is not None]


# ---- generation -------------------------------------------------------------

_NODE_SYSTEM = (
    "You are a knowledge-graph extractor. Read the numbered blocks of text below "
    "and identify the key concepts, entities, people, events, and claims discussed. "
    "Every node MUST cite at least one block by index plus a short verbatim quote "
    "copied exactly from that block — do not paraphrase the quote. "
    f"Return at most {MAX_NODES} of the most important nodes; merge duplicates."
)

_EDGE_SYSTEM = (
    "You are a knowledge-graph extractor. You are given the same numbered blocks of "
    "text plus a list of nodes already extracted from them. Identify relationships "
    "between these nodes (use the exact node ids given — do not invent new ones). "
    "Every edge MUST cite at least one block by index plus a short verbatim quote "
    "copied exactly from that block. "
    f"Return at most {MAX_EDGES} of the most important relationships."
)


async def generate_mind_map(parts: list[tuple[SourcePart, str | None]]) -> MindMap:
    """Two-pass mind-map generation over a notebook's source parts.

    `parts` is `[(source_part, source_title), ...]` in document order — callers
    fetch this via a join so we don't re-query inside this module.
    """
    blocks = _build_blocks(parts)
    if not blocks:
        raise ValueError("Cannot build a mind map from a notebook with no text.")
    rendered = _render_blocks(blocks)

    model = get_heavy_model()

    node_structured = model.with_structured_output(NodeExtractionResult)
    node_result = await node_structured.ainvoke(
        [HumanMessage(content=f"{_NODE_SYSTEM}\n\n{rendered}\n\nReturn the nodes.")],
    )
    if not isinstance(node_result, NodeExtractionResult):
        raise TypeError(f"Expected NodeExtractionResult, got {type(node_result).__name__}")

    nodes = [
        MindMapNode(
            id=n.id,
            label=n.label,
            kind=n.kind,
            citations=_resolve_citations(n.citations, blocks),
        )
        for n in node_result.nodes
    ]
    known_ids = {n.id for n in nodes}
    node_listing = "\n".join(f"- {n.id}: {n.label} ({n.kind})" for n in nodes)

    edge_structured = model.with_structured_output(EdgeExtractionResult)
    edge_result = await edge_structured.ainvoke(
        [
            HumanMessage(
                content=(
                    f"{_EDGE_SYSTEM}\n\nNODES:\n{node_listing}\n\nBLOCKS:\n{rendered}\n\n"
                    "Return the edges."
                ),
            ),
        ],
    )
    if not isinstance(edge_result, EdgeExtractionResult):
        raise TypeError(f"Expected EdgeExtractionResult, got {type(edge_result).__name__}")

    edges = [
        MindMapEdge(
            **{"from": e.from_id, "to": e.to_id},
            label=e.label,
            citations=_resolve_citations(e.citations, blocks),
        )
        for e in edge_result.edges
        if e.from_id in known_ids and e.to_id in known_ids
    ]

    return MindMap(nodes=nodes, edges=edges)
