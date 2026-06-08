"""Chunker tests.

The marquee acceptance criterion: for every chunk produced,
    source_text[chunk.char_start : chunk.char_end] == chunk.text

We assert this both on hand-crafted edge cases and on 1000 randomized inputs.
"""

import random
import string

import pytest

from pynote_core.chunker import chunk_text


def test_empty_text_yields_nothing() -> None:
    assert chunk_text("") == []
    assert chunk_text("   \n\t  ") == []


def test_short_text_yields_one_chunk_covering_everything() -> None:
    src = "Hello world."
    [c] = chunk_text(src)
    assert c.text == src
    assert (c.char_start, c.char_end) == (0, len(src))


def test_long_text_splits_into_multiple_chunks_with_overlap() -> None:
    paragraph = ("This is a sentence. " * 200).rstrip()  # ~3800 chars
    chunks = chunk_text(paragraph, target_chars=600, overlap_chars=100)

    assert len(chunks) >= 3
    # Chunks ordered by char_start, ascending.
    starts = [c.char_start for c in chunks]
    assert starts == sorted(starts)
    # Every chunk roundtrips.
    for c in chunks:
        assert paragraph[c.char_start : c.char_end] == c.text


def test_citation_contract_holds_on_random_inputs() -> None:
    """1000 random texts, every chunk: offsets must reconstruct text exactly."""
    rng = random.Random(20260531)
    alphabet = string.ascii_letters + string.digits + "   \n\n.,;:!?-—()[]\"'"

    for _ in range(1000):
        length = rng.randint(0, 5000)
        text = "".join(rng.choice(alphabet) for _ in range(length))
        target = rng.choice((400, 800, 1200))
        overlap = rng.choice((50, 150, 250))

        chunks = chunk_text(text, target_chars=target, overlap_chars=overlap)

        for c in chunks:
            assert c.char_start <= c.char_end
            assert 0 <= c.char_start <= len(text)
            assert 0 <= c.char_end <= len(text)
            assert text[c.char_start : c.char_end] == c.text, (
                f"offset mismatch at ({c.char_start},{c.char_end}) "
                f"target={target} overlap={overlap}"
            )


def test_no_runaway_on_token_less_input() -> None:
    """A massive string with no whitespace must still terminate and tile the input."""
    text = "x" * 10_000
    chunks = chunk_text(text, target_chars=500, overlap_chars=50)
    assert len(chunks) >= 1
    # Coverage: every input position appears in at least one chunk.
    covered = bytearray(len(text))
    for c in chunks:
        for i in range(c.char_start, c.char_end):
            covered[i] = 1
    assert sum(covered) == len(text)


@pytest.mark.parametrize(
    ("size", "target", "overlap"),
    [
        (1500, 1200, 200),
        (3000, 600, 100),
        (5000, 800, 0),  # overlap=0
    ],
)
def test_chunks_always_advance(size: int, target: int, overlap: int) -> None:
    """The two invariants we actually care about: forward progress and bounded reach."""
    from itertools import pairwise

    text = ("word " * (size // 5)).rstrip()
    chunks = chunk_text(text, target_chars=target, overlap_chars=overlap)
    if len(chunks) < 2:
        return
    # The chunker may stretch up to 200 chars past `target` to land on whitespace
    # (see chunker.py safety bound).
    max_step = target + 200
    for prev, cur in pairwise(chunks):
        step = cur.char_start - prev.char_start
        assert step > 0, "must advance"
        assert step <= max_step, f"step {step} > {max_step} (target+stretch)"
