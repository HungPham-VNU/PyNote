"""Structure-aware chunker.

Chunks align to document structure instead of blind char windows
(RAG_ROADMAP 3.1, sans Docling):

1. paragraphs (blank-line separated) pack greedily up to `target_chars`;
2. a paragraph larger than `target_chars` splits at sentence ends;
3. text with no usable boundaries (huge token-less runs) falls back to
   whitespace-snapped windows with `overlap_chars` overlap — the pre-3.1
   behavior, kept as the safety net.

Callers may pass `boundaries` — sorted char offsets such as section-heading
starts from the PDF parser — and no chunk will span one, so a retrieval hit
never mixes two sections. `section_paths` then maps chunk starts back to the
heading hierarchy ("3 Methods > 3.2 Training") for chunk.meta and the
contextual-embedding header (3.2).

Citation contract (acceptance test in M2): for every chunk produced,
    source_text[chunk.char_start : chunk.char_end] == chunk.text
must hold exactly — every chunk is a contiguous slice of the input. Tests
assert this on randomized inputs, including random boundaries.

300 tokens (~1200 chars) stays the size target from PLAN.md. Overlap now
applies only on the fallback path: a chunk that ends on a paragraph or
sentence boundary is self-contained and doesn't need bleed. Undersized
tails merge into the previous chunk instead of being dropped, so no text
is lost between chunks.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Sequence

DEFAULT_TARGET_CHARS = 1200  # ~300 tokens for English
DEFAULT_OVERLAP_CHARS = 200  # ~50 tokens (fallback windows only)
MIN_CHARS = 100  # merge slivers below this into the previous chunk

# Whitespace-stretch bound: how far past `target_chars` a fallback window may
# grow hunting for whitespace before giving up and cutting mid-word.
_MAX_STRETCH = 200

_PARA_BREAK = re.compile(r"\n[ \t]*\n+")
# End of sentence: terminal punctuation, optional closing quote/bracket
# (straight or curly; the escapes are the right double/single curly
# quotes), then whitespace. The next sentence starts after it.
_SENT_BREAK = re.compile(r"(?<=[.!?])[\"'\u201d\u2019)\]]*\s+")


@dataclass(frozen=True, slots=True)
class Chunk:
    text: str
    char_start: int
    char_end: int


def chunk_text(
    text: str,
    *,
    target_chars: int = DEFAULT_TARGET_CHARS,
    overlap_chars: int = DEFAULT_OVERLAP_CHARS,
    min_chars: int = MIN_CHARS,
    boundaries: Sequence[int] = (),
) -> list[Chunk]:
    """Split `text` into structure-aligned chunks.

    Returns chunks whose char_start/char_end index into the ORIGINAL `text`
    such that `text[c.char_start:c.char_end] == c.text` for every chunk.
    `boundaries` are hard cuts (e.g. heading offsets): no chunk spans one.
    """
    text = text or ""
    if not text.strip():
        return []

    cuts = sorted({b for b in boundaries if 0 < b < len(text)})
    if len(text) <= target_chars and not cuts:
        return [Chunk(text=text, char_start=0, char_end=len(text))]

    forced = set(cuts)
    out: list[Chunk] = []
    cur: tuple[int, int] | None = None  # accumulating (start, end)

    for s, e in _units(text, cuts):
        if cur is not None and (s in forced or e - cur[0] > target_chars):
            _emit(text, cur[0], cur[1], min_chars, forced, out)
            cur = None
        cur = (cur[0], e) if cur is not None else (s, e)
        if cur[1] - cur[0] > target_chars:
            # A single unit can exceed target (long paragraph): split it at
            # sentence ends. Packed units never exceed — see the flush above.
            _split_oversized(
                text, cur[0], cur[1], target_chars, overlap_chars, min_chars, forced, out
            )
            cur = None
    if cur is not None:
        _emit(text, cur[0], cur[1], min_chars, forced, out)

    return out


def _units(text: str, cuts: list[int]) -> list[tuple[int, int]]:
    """Non-blank paragraph spans, additionally split at every forced cut."""
    spans: list[tuple[int, int]] = []
    pos = 0
    for m in _PARA_BREAK.finditer(text):
        if m.start() > pos:
            spans.append((pos, m.start()))
        pos = m.end()
    if pos < len(text):
        spans.append((pos, len(text)))

    out: list[tuple[int, int]] = []
    for s, e in spans:
        for b in cuts:
            if s < b < e:
                if text[s:b].strip():
                    out.append((s, b))
                s = b
        if text[s:e].strip():
            out.append((s, e))
    return out


def _split_oversized(
    text: str,
    s: int,
    e: int,
    target: int,
    overlap: int,
    min_chars: int,
    forced: set[int],
    out: list[Chunk],
) -> None:
    """Split one oversized unit [s, e) at sentence ends, packing greedily.

    A stretch with no sentence break within `target` chars (tables, token
    soup) falls back to whitespace windows.
    """
    # Candidate cut points: each following-sentence start, then the unit end.
    bounds = [s + m.end() for m in _SENT_BREAK.finditer(text[s:e])]
    bounds.append(e)

    ws = s
    j = 0
    while ws < e:
        while j < len(bounds) and bounds[j] <= ws:
            j += 1
        if j >= len(bounds):
            break
        k = j
        while k + 1 < len(bounds) and bounds[k + 1] - ws <= target:
            k += 1
        if bounds[k] - ws <= target:
            _emit(text, ws, bounds[k], min_chars, forced, out)
            ws = bounds[k]
            j = k + 1
        else:
            # Sentence itself exceeds target — window it on whitespace.
            _ws_windows(text, ws, bounds[j], target, overlap, min_chars, forced, out)
            ws = bounds[j]
            j += 1


def _ws_windows(
    text: str,
    a: int,
    b: int,
    target: int,
    overlap: int,
    min_chars: int,
    forced: set[int],
    out: list[Chunk],
) -> None:
    """Whitespace-snapped overlapping windows over [a, b) — the fallback path."""
    pos = a
    while pos < b:
        end = min(pos + target, b)
        if end < b:
            stretched = end
            while stretched < b and not text[stretched].isspace():
                stretched += 1
                if stretched - end > _MAX_STRETCH:  # avoid runaway on token-less text
                    stretched = end
                    break
            end = stretched
        _emit(text, pos, end, min_chars, forced, out)
        if end >= b:
            break
        next_pos = max(pos + 1, end - overlap)
        while next_pos < end and not text[next_pos].isspace():
            next_pos += 1
        if next_pos == pos:  # guarantee progress
            next_pos = end
        pos = next_pos


def _emit(text: str, s: int, e: int, min_chars: int, forced: set[int], out: list[Chunk]) -> None:
    """Append text[s:e) as a chunk; merge slivers into the previous chunk.

    Merging extends the previous chunk's end (both are slices of the same
    text, so the contract survives). A sliver that *starts* a section stays
    its own chunk rather than bleeding into the previous section.
    """
    body = text[s:e]
    if not body.strip():
        return
    if len(body.strip()) < min_chars and out and s not in forced:
        prev = out[-1]
        if prev.char_end < e:
            out[-1] = Chunk(text=text[prev.char_start : e], char_start=prev.char_start, char_end=e)
        return
    out.append(Chunk(text=body, char_start=s, char_end=e))


# ---- section paths ----------------------------------------------------------


def section_paths(
    chunk_starts: Sequence[int],
    headings: Sequence[dict[str, Any]],
    stack: list[tuple[int, str]],
) -> list[list[str]]:
    """Section path in effect at each chunk start, given heading events.

    `headings` are dicts with `start` (char offset), `level` (1 = topmost)
    and `text`, as produced by the PDF parser. `stack` is (level, text)
    state MUTATED in place so callers can carry it across parts — headings
    stay open across page breaks until a same-or-higher heading closes them.
    Headings positioned after the last chunk are still applied so the next
    part starts from the right state.
    """
    events = sorted(headings, key=lambda h: int(h["start"]))
    out: list[list[str]] = []
    i = 0
    for start in chunk_starts:
        while i < len(events) and int(events[i]["start"]) <= start:
            _push_heading(stack, events[i])
            i += 1
        out.append([t for _, t in stack])
    while i < len(events):
        _push_heading(stack, events[i])
        i += 1
    return out


def _push_heading(stack: list[tuple[int, str]], h: dict[str, Any]) -> None:
    level = int(h.get("level", 1))
    while stack and stack[-1][0] >= level:
        stack.pop()
    stack.append((level, str(h["text"])))
