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
