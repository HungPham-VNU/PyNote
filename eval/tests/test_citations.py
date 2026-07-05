"""Pure-function tests for the citation parser.

No model, no DB. We construct realistic Anthropic-shaped response payloads and
assert the parser pulls out the right citations and grades roundtrip correctly.
"""

from __future__ import annotations

from uuid import UUID

from eval.prototype.citations import (
    fidelity,
    pack_search_results,
    parse_response,
)
from eval.prototype.retrieval import Hit


def _hit(text: str, idx: int = 0) -> Hit:
    return Hit(
        chunk_id=UUID(int=idx + 1),
        source_id=UUID(int=100 + idx),
        source_part_id=UUID(int=200 + idx),
        source_title=f"doc-{idx}",
        page=idx + 1,
        text=text,
        char_start=0,
        char_end=len(text),
        score=1.0 - idx * 0.01,
    )


def test_citation_includes_page_and_title() -> None:
    """Citations must carry page + source_title for M5's PDF-jump UX."""
    chunk = "abcdef"
    hits = [_hit(chunk, 3)]  # page=4, source_title="doc-3"
    content = [
        {
            "type": "text",
            "text": "abc",
            "citations": [
                {
                    "type": "search_result_location",
                    "cited_text": "abc",
                    "search_result_index": 0,
                    "start_char_index": 0,
                    "end_char_index": 3,
                }
            ],
        }
    ]
    answer = parse_response(content, hits)
    assert answer.citations[0].page == 4
    assert answer.citations[0].source_title == "doc-3"


def test_citation_recovers_span_when_offsets_are_bogus() -> None:
    """Some providers/gateways return `cited_text` but 0/0 offsets.

    We must still ground the citation by locating the quote in the chunk and
    reporting the recovered offsets, not a zero-width failed roundtrip.
    """
    chunk = "Photosynthesis converts light into chemical energy."
    hits = [_hit(chunk, 0)]
    content = [
        {
            "type": "text",
            "text": "It makes chemical energy.",
            "citations": [
                {
                    "type": "search_result_location",
                    "cited_text": "chemical energy",
                    "search_result_index": 0,
                    "start_char_index": 0,
                    "end_char_index": 0,
                }
            ],
        }
    ]
    [cit] = parse_response(content, hits).citations
    assert cit.roundtrip_ok is True
    assert cit.chunk_text_slice == "chemical energy"
    assert chunk[cit.start_char_index : cit.end_char_index] == "chemical energy"


def test_citation_roundtrip_fails_when_quote_absent() -> None:
    """If the quote isn't in the chunk at all, roundtrip must stay False."""
    hits = [_hit("nothing relevant here", 0)]
    content = [
        {
            "type": "text",
            "text": "x",
            "citations": [
                {
                    "type": "search_result_location",
                    "cited_text": "totally different text",
                    "search_result_index": 0,
                    "start_char_index": 0,
                    "end_char_index": 0,
                }
            ],
        }
    ]
    [cit] = parse_response(content, hits).citations
    assert cit.roundtrip_ok is False


# ---- pack_search_results ---------------------------------------------------


def test_pack_aligns_index_with_hit_position() -> None:
    hits = [_hit("first hit text", 0), _hit("second hit text", 1)]
    blocks = pack_search_results(hits)
    assert len(blocks) == 2
    assert blocks[0]["type"] == "search_result"
    assert blocks[0]["citations"] == {"enabled": True}
    assert blocks[0]["content"][0]["text"] == "first hit text"
    assert blocks[1]["content"][0]["text"] == "second hit text"


def test_pack_empty_hits_yields_no_blocks() -> None:
    assert pack_search_results([]) == []


# ---- parse_response --------------------------------------------------------


def test_parse_extracts_text_and_citations() -> None:
    chunk_text = "The grass is green and very lush."
    hits = [_hit(chunk_text, 0)]
    # "grass is green" lives at [4:18] inside chunk_text.
    cited = chunk_text[4:18]
    content = [
        {"type": "text", "text": "Based on the document, "},
        {
            "type": "text",
            "text": cited,
            "citations": [
                {
                    "type": "search_result_location",
                    "cited_text": cited,
                    "search_result_index": 0,
                    "start_char_index": 4,
                    "end_char_index": 18,
                }
            ],
        },
        {"type": "text", "text": "."},
    ]
    answer = parse_response(content, hits)

    assert answer.text == f"Based on the document, {cited}."
    assert len(answer.citations) == 1
    c = answer.citations[0]
    assert c.chunk_id == hits[0].chunk_id
    assert c.cited_text == cited
    assert c.chunk_text_slice == cited
    assert c.roundtrip_ok is True


def test_parse_recovers_drifted_offsets_when_quote_present() -> None:
    hits = [_hit("The sky is blue.", 0)]
    # cited_text says "blue" but offsets point at "sky " — drift. Because the
    # quote genuinely appears in the chunk we recover it (correcting the
    # offsets) rather than reporting a failed roundtrip.
    content = [
        {
            "type": "text",
            "text": "blue",
            "citations": [
                {
                    "type": "search_result_location",
                    "cited_text": "blue",
                    "search_result_index": 0,
                    "start_char_index": 4,
                    "end_char_index": 8,
                }
            ],
        }
    ]
    answer = parse_response(content, hits)
    assert len(answer.citations) == 1
    c = answer.citations[0]
    assert c.cited_text == "blue"
    assert c.chunk_text_slice == "blue"
    assert c.roundtrip_ok is True
    assert "The sky is blue."[c.start_char_index : c.end_char_index] == "blue"


def test_parse_skips_malformed_or_out_of_range_citations() -> None:
    hits = [_hit("Hello world.", 0)]
    content = [
        {
            "type": "text",
            "text": "yes",
            "citations": [
                {"type": "search_result_location", "search_result_index": 99},  # OOR
                {"type": "tool_use"},  # wrong type
                "not a dict",
            ],
        }
    ]
    answer = parse_response(content, hits)
    assert answer.text == "yes"
    assert answer.citations == []


def test_parse_accepts_char_location_alias() -> None:
    """Older Anthropic responses use `char_location` instead of `search_result_location`."""
    hits = [_hit("Important sentence.", 0)]
    content = [
        {
            "type": "text",
            "text": "Important sentence.",
            "citations": [
                {
                    "type": "char_location",
                    "cited_text": "Important sentence.",
                    "search_result_index": 0,
                    "start_char_index": 0,
                    "end_char_index": 19,
                }
            ],
        }
    ]
    answer = parse_response(content, hits)
    assert len(answer.citations) == 1
    assert answer.citations[0].roundtrip_ok is True


def test_parse_accepts_plain_string_content() -> None:
    """When Claude returns plain text (refusal, no-citation answer), no crash."""
    answer = parse_response("I cannot find the answer in the sources.", hits=[_hit("x")])
    assert "cannot find" in answer.text
    assert answer.citations == []


# ---- fidelity --------------------------------------------------------------


def test_fidelity_is_one_when_no_citations() -> None:
    answer = parse_response([{"type": "text", "text": "just text"}], hits=[])
    assert fidelity(answer) == 1.0


def test_fidelity_counts_roundtrip_fraction() -> None:
    chunk = "alpha beta gamma."  # alpha=[0:5], beta=[6:10], gamma=[11:16]
    hits = [_hit(chunk, 0)]
    content = [
        {
            "type": "text",
            "text": "alpha and gamma",
            "citations": [
                {
                    "type": "search_result_location",
                    "cited_text": "alpha",
                    "search_result_index": 0,
                    "start_char_index": 0,
                    "end_char_index": 5,
                },
                {
                    "type": "search_result_location",
                    "cited_text": "gamma",
                    "search_result_index": 0,
                    "start_char_index": 11,
                    "end_char_index": 16,
                },
                {  # genuine failure: "delta" is nowhere in the chunk
                    "type": "search_result_location",
                    "cited_text": "delta",
                    "search_result_index": 0,
                    "start_char_index": 0,
                    "end_char_index": 4,
                },
            ],
        }
    ]
    answer = parse_response(content, hits)
    # 2 of 3 roundtrip cleanly; the ungrounded "delta" quote does not.
    assert abs(fidelity(answer) - 2 / 3) < 1e-9
