"""PDF parser: generates a 3-page PDF in memory, parses it, asserts contents.

No external fixtures — keeps tests hermetic.
"""

from pathlib import Path

import pymupdf
import pytest

from pynote_core.parsers import parse
from pynote_core.parsers.pdf import parse_pdf


def _make_pdf(tmp_path: Path, pages: list[str]) -> Path:
    path = tmp_path / "fixture.pdf"
    doc = pymupdf.open()
    for body in pages:
        page = doc.new_page()
        page.insert_text((72, 72), body, fontsize=12)
    doc.save(path)
    doc.close()
    return path


def test_parse_pdf_yields_one_part_per_page(tmp_path: Path) -> None:
    pdf = _make_pdf(tmp_path, ["Hello page one.", "Second page text.", "Third."])
    parts = list(parse_pdf(pdf))

    assert [p.ordinal for p in parts] == [0, 1, 2]
    assert [p.page for p in parts] == [1, 2, 3]
    assert "Hello page one." in parts[0].text
    assert "Second page text." in parts[1].text
    assert "Third." in parts[2].text

    # bbox should be populated for every part.
    for p in parts:
        assert p.bbox is not None
        assert {"x0", "y0", "x1", "y1"}.issubset(p.bbox.keys())


def test_parser_registry_dispatches_to_pdf(tmp_path: Path) -> None:
    pdf = _make_pdf(tmp_path, ["Registry test."])
    parts = parse("pdf", pdf)
    assert len(parts) == 1
    assert "Registry test." in parts[0].text


def test_parser_registry_rejects_unknown_kind(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="No loader registered"):
        parse("docx", tmp_path / "missing.docx")


# ---- hygiene passes (RAG_ROADMAP 2.3) ---------------------------------------


def test_repeated_headers_and_page_numbers_stripped(tmp_path: Path) -> None:
    bodies = [
        "The introduction motivates the retrieval problem.",
        "Chunking strategy details follow in this section.",
        "Embedding models are compared across benchmarks.",
        "Reranking improves precision at low k values.",
        "The conclusion summarizes citation grounding results.",
    ]
    pages = [
        f"Annual Report 2026\n{body}\nAnother line of real prose here.\nPage {i}"
        for i, body in enumerate(bodies, start=1)
    ]
    pdf = _make_pdf(tmp_path, pages)
    parts = list(parse_pdf(pdf))

    for i, (p, body) in enumerate(zip(parts, bodies), start=1):
        assert "Annual Report 2026" not in p.text
        assert f"Page {i}" not in p.text  # digit-normalized match
        assert body in p.text


def test_unique_edge_lines_survive(tmp_path: Path) -> None:
    pages = [
        "Introduction to widgets\nSome body.",
        "Methods for widget testing\nMore body.",
        "Conclusions about widgets\nFinal body.",
    ]
    pdf = _make_pdf(tmp_path, pages)
    parts = list(parse_pdf(pdf))
    assert "Introduction to widgets" in parts[0].text
    assert "Methods for widget testing" in parts[1].text


def test_hyphenated_line_wrap_joined(tmp_path: Path) -> None:
    pdf = _make_pdf(tmp_path, ["The results show a marked improve-\nment in recall."])
    parts = list(parse_pdf(pdf))
    assert "improvement" in parts[0].text
    assert "improve-" not in parts[0].text


def test_list_dashes_not_joined(tmp_path: Path) -> None:
    # "- Alpha" after a line break must not be glued to the previous word:
    # the continuation is uppercase, so the wrap regex leaves it alone.
    pdf = _make_pdf(tmp_path, ["Items considered-\nAlpha and beta."])
    parts = list(parse_pdf(pdf))
    assert "considered-\nAlpha" in parts[0].text
