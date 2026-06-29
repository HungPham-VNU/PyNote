"""Char-based chunker.

For M2: flat level-0 chunking. The schema has parent_chunk_id + level fields
for the hierarchy that lands when we adopt Docling for section detection.

Citation contract (acceptance test in M2): for every chunk produced,
    source_text[chunk.char_start : chunk.char_end] == chunk.text
must hold exactly. Tests assert this on randomized inputs.

300 tokens with 50-token overlap is the PLAN.md target. We approximate via
~4 chars/token (English avg): 1200 chars / 200 overlap. The exact token count
is unimportant for chunking — the reranker compensates downstream.
"""

from dataclasses import dataclass

DEFAULT_TARGET_CHARS = 1200  # ~300 tokens for English
DEFAULT_OVERLAP_CHARS = 200  # ~50 tokens
MIN_CHARS = 100  # don't emit useless slivers


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
) -> list[Chunk]:
    """Split `text` into overlapping windows aligned to whitespace.

    Returns chunks whose char_start/char_end index into the ORIGINAL `text`
    such that `text[c.char_start:c.char_end] == c.text` for every chunk.
    """
    text = text or ""
    if len(text) <= target_chars:
        stripped = text.strip()
        if not stripped:
            return []
        return [Chunk(text=text, char_start=0, char_end=len(text))]

    chunks: list[Chunk] = []
    pos = 0
    n = len(text)

    while pos < n:
        end = min(pos + target_chars, n)
        # Snap end to the next whitespace so we don't break mid-word.
        if end < n:
            stretched = end
            while stretched < n and not text[stretched].isspace():
                stretched += 1
                if stretched - end > 200:  # safety: avoid runaway on token-less text
                    stretched = end
                    break
            end = stretched

        body = text[pos:end]
        if len(body.strip()) >= min_chars:
            chunks.append(Chunk(text=body, char_start=pos, char_end=end))

        if end >= n:
            break

        # Step forward: end - overlap, snapped to whitespace.
        next_pos = max(pos + 1, end - overlap_chars)
        while next_pos < end and not text[next_pos].isspace():
            next_pos += 1
        if next_pos == pos:  # guarantee progress
            next_pos = end
        pos = next_pos

    return chunks
