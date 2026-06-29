"""PDF loader (PyMuPDF).

One ParsedPart per page. Text is extracted in natural reading order
(`get_text("text")`) — fast and predictable. We capture the page rect as bbox
so later milestones can lay out highlights.

M2 will likely swap or supplement this with Docling for proper section
detection; the loader contract stays the same.
"""

from collections.abc import Iterator
from pathlib import Path

import pymupdf

from pynote_core.parsers.types import ParsedPart


def parse_pdf(path: Path) -> Iterator[ParsedPart]:
    with pymupdf.open(path) as doc:
        for ordinal, page in enumerate(doc):
            text = page.get_text("text").strip()
            rect = page.rect
            yield ParsedPart(
                ordinal=ordinal,
                page=ordinal + 1,  # 1-based for humans
                text=text,
                bbox={
                    "x0": float(rect.x0),
                    "y0": float(rect.y0),
                    "x1": float(rect.x1),
                    "y1": float(rect.y1),
                    "rotation": int(page.rotation),
                },
            )
