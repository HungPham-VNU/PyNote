"""Citation packing + parsing + validation.

Used by:
  - eval/prototype/m3.py             (CLI grading)
  - pynote_core.chat_graph           (M4 chat — map_citations node)

Pure functions: no I/O, no model calls. Drives the M4 chat-graph's
`map_citations` node verbatim.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from uuid import UUID

    from pynote_core.retrieval import Hit


def pack_search_results(hits: list[Hit]) -> list[dict[str, Any]]:
    """Build Anthropic `search_result` content blocks, one per hit.

    Index ordering matters: Claude returns `search_result_index` referencing
    the position here, so we keep `hits[i]` aligned with the block at index `i`.
    """
    return [
        {
            "type": "search_result",
            "title": h.source_title or "Untitled source",
            "source": f"pynote://chunk/{h.chunk_id}",
            "citations": {"enabled": True},
            "content": [{"type": "text", "text": h.text}],
        }
        for h in hits
    ]


@dataclass(frozen=True, slots=True)
class ResolvedCitation:
    """One citation, mapped back to the source it grounds in."""

    cited_text: str
    search_result_index: int
    start_char_index: int
    end_char_index: int
    chunk_id: UUID
    source_id: UUID
    source_part_id: UUID
    # Display metadata pulled from the matching Hit — populated for M5's PDF jump.
    source_title: str | None
    page: int | None
    # Roundtripped slice from chunk.text using the model's offsets:
    chunk_text_slice: str
    # True iff `chunk_text_slice == cited_text`. Our "fully grounded" definition.
    roundtrip_ok: bool


@dataclass(frozen=True, slots=True)
class ParsedAnswer:
    """The model's answer plus every citation we could parse out of it."""

    text: str
    citations: list[ResolvedCitation]


def parse_response(content: Any, hits: list[Hit]) -> ParsedAnswer:
    """Walk Claude's content blocks, extracting text + citations.

    Accepts both `search_result_location` (newer) and `char_location` (older)
    citation types. Blocks of other shapes (text without citations, refusals,
    tool uses) are passed through as text. Malformed citations are skipped.
    """
    blocks = _normalize_blocks(content)

    text_parts: list[str] = []
    citations: list[ResolvedCitation] = []

    for block in blocks:
        if not isinstance(block, dict):
            continue
        if block.get("type") != "text":
            continue
        text_parts.append(str(block.get("text", "")))
        for c in block.get("citations") or []:
            if not isinstance(c, dict):
                continue
            if c.get("type") not in ("search_result_location", "char_location"):
                continue
            idx = c.get("search_result_index")
            if not isinstance(idx, int) or not (0 <= idx < len(hits)):
                continue
            start = int(c.get("start_char_index", 0))
            end = int(c.get("end_char_index", start))
            hit = hits[idx]
            slice_ = hit.text[start:end]
            citations.append(
                ResolvedCitation(
                    cited_text=str(c.get("cited_text", "")),
                    search_result_index=idx,
                    start_char_index=start,
                    end_char_index=end,
                    chunk_id=hit.chunk_id,
                    source_id=hit.source_id,
                    source_part_id=hit.source_part_id,
                    source_title=hit.source_title,
                    page=hit.page,
                    chunk_text_slice=slice_,
                    roundtrip_ok=slice_ == str(c.get("cited_text", "")),
                )
            )

    return ParsedAnswer(text="".join(text_parts), citations=citations)


def citation_to_jsonable(c: ResolvedCitation) -> dict[str, Any]:
    """JSON-safe shape persisted on `message.citations_jsonb` and sent to the web."""
    return {
        "cited_text": c.cited_text,
        "search_result_index": c.search_result_index,
        "start_char_index": c.start_char_index,
        "end_char_index": c.end_char_index,
        "chunk_id": str(c.chunk_id),
        "source_id": str(c.source_id),
        "source_part_id": str(c.source_part_id),
        "source_title": c.source_title,
        "page": c.page,
        "roundtrip_ok": c.roundtrip_ok,
    }


def fidelity(answer: ParsedAnswer) -> float:
    """Fraction of citations that roundtrip — the M3 grading metric.

    Returns 1.0 when there are no citations (no claims = no failures).
    """
    if not answer.citations:
        return 1.0
    ok = sum(1 for c in answer.citations if c.roundtrip_ok)
    return ok / len(answer.citations)


def _normalize_blocks(content: Any) -> list[Any]:
    """Accept both LangChain Message.content and raw dict lists."""
    if isinstance(content, list):
        return content
    if isinstance(content, str):
        return [{"type": "text", "text": content}]
    return []
