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

Structure detection (RAG_ROADMAP 3.1, lightweight variant): headings are
detected from font metadata — a short line set noticeably larger than the
document's body size (or bold at body size) is a heading, and distinct
heading sizes rank into levels. Detected headings are located in the cleaned
page text and emitted as `ParsedPart.headings` so the chunker can treat them
as hard section boundaries and build section paths. Docling remains the
heavyweight upgrade path (tables, multi-column reading order); this covers
the heading/boundary share of it with zero new dependencies.
"""

import re
from collections import Counter
from collections.abc import Iterator
from pathlib import Path
from typing import Any

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


# ---- heading detection (RAG_ROADMAP 3.1) ------------------------------------

# Headings are short. Longer large-font lines are usually pull quotes/banners.
_MAX_HEADING_CHARS = 100
# A line is heading-sized when ≥ 12% larger than body text — wide enough to
# clear rounding jitter, narrow enough to catch conservative heading scales.
_HEADING_SIZE_RATIO = 1.12
# Deeper heading sizes all collapse to this level; bold-at-body-size headings
# land one below the smallest distinct heading size.
_MAX_HEADING_LEVEL = 3
_BOLD_FLAG = 1 << 4  # pymupdf span flag


def _page_lines(page: pymupdf.Page) -> list[tuple[str, float, bool]]:
    """(text, max span size, any-span-bold) per rendered text line."""
    out: list[tuple[str, float, bool]] = []
    for block in page.get_text("dict")["blocks"]:  # type: ignore[no-untyped-call]
        if block.get("type") != 0:  # 0 = text block
            continue
        for line in block.get("lines", []):
            spans = line.get("spans", [])
            text = "".join(s.get("text", "") for s in spans).strip()
            if not text:
                continue
            size = round(max(float(s.get("size", 0.0)) for s in spans), 1)
            bold = any(int(s.get("flags", 0)) & _BOLD_FLAG for s in spans)
            out.append((text, size, bold))
    return out


def _body_size(page_lines: list[list[tuple[str, float, bool]]]) -> tuple[float, bool]:
    """(body font size, whether body text is predominantly bold).

    Body size is the size carrying the most characters. When the body itself
    is bold, boldness stops being a heading signal.
    """
    weights: Counter[float] = Counter()
    bold_chars: Counter[float] = Counter()
    for lines in page_lines:
        for text, size, bold in lines:
            weights[size] += len(text)
            if bold:
                bold_chars[size] += len(text)
    if not weights:
        return 0.0, False
    body = weights.most_common(1)[0][0]
    return body, bold_chars[body] * 2 > weights[body]


def _is_heading_line(text: str, size: float, bold: bool, body: float, *, allow_bold: bool) -> bool:
    if len(text) > _MAX_HEADING_CHARS or not any(ch.isalpha() for ch in text):
        return False
    if text.endswith((".", ",")):  # full sentences aren't headings
        return False
    return size >= body * _HEADING_SIZE_RATIO or (allow_bold and bold and size >= body)


def _heading_levels(
    page_lines: list[list[tuple[str, float, bool]]], body: float, *, allow_bold: bool
) -> dict[float, int]:
    """Rank distinct heading sizes: biggest font → level 1."""
    sizes = sorted(
        {
            size
            for lines in page_lines
            for text, size, bold in lines
            if _is_heading_line(text, size, bold, body, allow_bold=allow_bold)
            and size >= body * _HEADING_SIZE_RATIO
        },
        reverse=True,
    )
    return {s: min(i + 1, _MAX_HEADING_LEVEL) for i, s in enumerate(sizes)}


def _locate_headings(
    cleaned: str,
    lines: list[tuple[str, float, bool]],
    body: float,
    levels: dict[float, int],
    *,
    allow_bold: bool,
) -> list[dict[str, Any]] | None:
    """Map detected heading lines to char offsets in the cleaned page text.

    Walks with a cursor so repeated heading strings resolve in order. Lines
    the hygiene passes removed or rewrote simply don't match — skipped.
    """
    out: list[dict[str, Any]] = []
    cursor = 0
    for text, size, bold in lines:
        if not _is_heading_line(text, size, bold, body, allow_bold=allow_bold):
            continue
        start = cleaned.find(text, cursor)
        if start < 0:
            continue
        # Bold-at-body-size headings rank below every distinct heading size.
        level = levels.get(size, min(len(levels) + 1, _MAX_HEADING_LEVEL))
        out.append({"text": text, "level": level, "start": start})
        cursor = start + len(text)
    return out or None


def parse_pdf(path: Path) -> Iterator[ParsedPart]:
    with pymupdf.open(path) as doc:  # type: ignore[no-untyped-call]
        pages = []
        page_lines: list[list[tuple[str, float, bool]]] = []
        for page in doc:
            rect = page.rect
            page_lines.append(_page_lines(page))
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
    body, bold_body = _body_size(page_lines)
    allow_bold = not bold_body
    levels = _heading_levels(page_lines, body, allow_bold=allow_bold)
    for ordinal, (text, bbox) in enumerate(pages):
        cleaned = _dehyphenate(_strip_boilerplate(text, boilerplate)).strip()
        yield ParsedPart(
            ordinal=ordinal,
            page=ordinal + 1,  # 1-based for humans
            text=cleaned,
            bbox=bbox,
            headings=_locate_headings(
                cleaned, page_lines[ordinal], body, levels, allow_bold=allow_bold
            ),
        )
