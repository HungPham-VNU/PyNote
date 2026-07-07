"""PDF loader (PyMuPDF).

One ParsedPart per page. Text is extracted in natural reading order
(`get_text("text")`) — fast and predictable. We capture the page rect as bbox
so later milestones can lay out highlights.

Hygiene passes (RAG_ROADMAP 2.3) applied before parts are yielded:
  - repeated header/footer lines (page numbers, running titles) are stripped —
    they'd otherwise pollute every chunk's embedding and tsvector;
  - hyphenated line wraps are joined ("improve-\\nment" → "improvement") so
    split words don't hide from retrieval.
Both run at parse time, so `source_part.text` is stored clean and the
citation contract binds the cleaned text.

Docling (RAG_ROADMAP 3.1) will supplement this with section detection; the
loader contract stays the same.
"""

import re
from collections import Counter
from collections.abc import Iterator
from pathlib import Path

import pymupdf

from pynote_core.parsers.types import ParsedPart

# How many non-empty lines at each page edge are candidate headers/footers.
_EDGE_LINES = 2
# A normalized edge line is boilerplate when it appears on >60% of pages
# (and at least 3), so a genuine sentence repeated once isn't stripped.
_BOILERPLATE_RATIO = 0.6
_BOILERPLATE_MIN_PAGES = 3

_DIGITS = re.compile(r"\d+")
# Join a word broken across a line break by a hyphen. Requiring a lowercase
# continuation avoids gluing list items like "- Alpha"; genuine hyphenated
# compounds split across lines lose the hyphen, an accepted tradeoff.
_HYPHEN_WRAP = re.compile(r"(?<=\w)-\n(?=[a-z])")


def _normalize_line(line: str) -> str:
    """Fold digits so 'Page 3' / 'Page 4' count as the same boilerplate line."""
    return _DIGITS.sub("#", line.strip()).casefold()


def _edge_lines(text: str) -> list[str]:
    lines = [ln for ln in text.splitlines() if ln.strip()]
    return lines[:_EDGE_LINES] + lines[-_EDGE_LINES:] if lines else []


def _boilerplate_lines(page_texts: list[str]) -> set[str]:
    """Normalized edge lines that repeat across enough pages to be chrome."""
    threshold = max(_BOILERPLATE_MIN_PAGES, int(len(page_texts) * _BOILERPLATE_RATIO) + 1)
    counts: Counter[str] = Counter()
    for text in page_texts:
        counts.update(set(map(_normalize_line, _edge_lines(text))))
    return {line for line, n in counts.items() if n >= threshold}


def _strip_boilerplate(text: str, boilerplate: set[str]) -> str:
    """Drop boilerplate lines, but only from the page edges where they live —
    body text that happens to match is left alone."""
    if not boilerplate:
        return text
    lines = text.splitlines()
    nonempty = [i for i, ln in enumerate(lines) if ln.strip()]
    edge_idx = set(nonempty[:_EDGE_LINES] + nonempty[-_EDGE_LINES:])
    stripped = "\n".join(
        ln
        for i, ln in enumerate(lines)
        if i not in edge_idx or _normalize_line(ln) not in boilerplate
    )
    # Degenerate guard: a page that was ALL boilerplate (tiny pages whose edge
    # windows cover everything) keeps its original text rather than vanishing.
    return stripped if stripped.strip() else text


def _dehyphenate(text: str) -> str:
    return _HYPHEN_WRAP.sub("", text)


def parse_pdf(path: Path) -> Iterator[ParsedPart]:
    with pymupdf.open(path) as doc:  # type: ignore[no-untyped-call]
        pages = []
        for page in doc:
            rect = page.rect
            pages.append(
                (
                    page.get_text("text"),
                    {
                        "x0": float(rect.x0),
                        "y0": float(rect.y0),
                        "x1": float(rect.x1),
                        "y1": float(rect.y1),
                        "rotation": int(page.rotation),
                    },
                )
            )

    boilerplate = _boilerplate_lines([text for text, _ in pages])
    for ordinal, (text, bbox) in enumerate(pages):
        cleaned = _dehyphenate(_strip_boilerplate(text, boilerplate)).strip()
        yield ParsedPart(
            ordinal=ordinal,
            page=ordinal + 1,  # 1-based for humans
            text=cleaned,
            bbox=bbox,
        )
