"""Chunker tests.

The marquee acceptance criterion: for every chunk produced,
    source_text[chunk.char_start : chunk.char_end] == chunk.text

We assert this both on hand-crafted edge cases and on 1000 randomized inputs.
"""

import random
import string

import pytest

from pynote_core.chunker import chunk_text, section_paths


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


# ---- structure awareness (RAG_ROADMAP 3.1) ----------------------------------


def test_paragraphs_are_not_split_when_they_fit() -> None:
    """Chunks align to paragraph boundaries: no chunk starts or ends mid-paragraph."""
    paras = [
        f"Paragraph {i} talks about topic {i} in a couple of sentences. More text {i}."
        for i in range(8)
    ]
    src = "\n\n".join(paras)
    chunks = chunk_text(src, target_chars=200, min_chars=10)

    para_starts = {src.index(p) for p in paras}
    para_ends = {src.index(p) + len(p) for p in paras}
    assert len(chunks) > 1
    for c in chunks:
        assert c.char_start in para_starts
        assert c.char_end in para_ends
    for c in chunks:
        assert src[c.char_start : c.char_end] == c.text


def test_oversized_paragraph_splits_at_sentence_ends() -> None:
    """Every non-final chunk of a long paragraph ends on a sentence boundary."""
    src = ("The model retrieves relevant chunks from storage. " * 40).rstrip()
    chunks = chunk_text(src, target_chars=300)

    assert len(chunks) > 2
    for c in chunks[:-1]:
        assert c.text.rstrip().endswith("."), f"chunk ends mid-sentence: {c.text[-40:]!r}"
    for c in chunks:
        assert src[c.char_start : c.char_end] == c.text


def test_forced_boundaries_are_never_spanned() -> None:
    """A chunk never crosses a section boundary (heading offset)."""
    section = "Heading line\n" + "Body sentence with several words repeated here. " * 10
    src = "\n\n".join([section] * 4)
    boundaries = [i for i in range(len(src)) if src.startswith("Heading line", i)][1:]

    chunks = chunk_text(src, target_chars=5000, boundaries=boundaries)

    assert len(chunks) >= len(boundaries) + 1  # at least one chunk per section
    for c in chunks:
        for b in boundaries:
            assert not (c.char_start < b < c.char_end), f"chunk spans boundary at {b}"
        assert src[c.char_start : c.char_end] == c.text


def test_trailing_sliver_merges_into_previous_chunk() -> None:
    """Undersized tails extend the previous chunk instead of being dropped."""
    src = (
        "A full sentence about retrieval systems and their chunking. " * 20
    ).rstrip() + "\n\nTiny tail."
    chunks = chunk_text(src, target_chars=400, min_chars=100)

    assert chunks[-1].char_end == len(src), "tail text must not be lost"
    for c in chunks:
        assert src[c.char_start : c.char_end] == c.text


def test_citation_contract_holds_with_random_boundaries() -> None:
    """Roundtrip must survive arbitrary forced boundaries."""
    rng = random.Random(20260708)
    alphabet = string.ascii_letters + string.digits + "   \n\n.,;:!?-—()[]\"'"

    for _ in range(300):
        length = rng.randint(0, 4000)
        text = "".join(rng.choice(alphabet) for _ in range(length))
        n_bounds = rng.randint(0, 8)
        boundaries = sorted(rng.randint(0, max(length, 1)) for _ in range(n_bounds))

        chunks = chunk_text(text, target_chars=rng.choice((300, 800)), boundaries=boundaries)

        for c in chunks:
            assert text[c.char_start : c.char_end] == c.text


# ---- section paths -----------------------------------------------------------


def test_section_paths_basic_hierarchy() -> None:
    headings = [
        {"text": "3 Methods", "level": 1, "start": 10},
        {"text": "3.2 Training", "level": 2, "start": 200},
    ]
    stack: list[tuple[int, str]] = []
    paths = section_paths([0, 50, 250], headings, stack)

    assert paths == [[], ["3 Methods"], ["3 Methods", "3.2 Training"]]


def test_section_paths_same_level_replaces() -> None:
    headings = [
        {"text": "3 Methods", "level": 1, "start": 0},
        {"text": "3.2 Training", "level": 2, "start": 100},
        {"text": "4 Results", "level": 1, "start": 300},
    ]
    stack: list[tuple[int, str]] = []
    paths = section_paths([150, 350], headings, stack)

    assert paths == [["3 Methods", "3.2 Training"], ["4 Results"]]


def test_section_paths_state_carries_across_parts() -> None:
    """A section opened on page 1 stays open for page 2's chunks."""
    stack: list[tuple[int, str]] = []
    section_paths([0], [{"text": "Intro", "level": 1, "start": 0}], stack)
    # Page 2: no headings of its own.
    paths = section_paths([0, 500], [], stack)

    assert paths == [["Intro"], ["Intro"]]


def test_section_paths_applies_headings_after_last_chunk() -> None:
    """A heading past the last chunk still mutates state for the next part."""
    stack: list[tuple[int, str]] = []
    section_paths([0], [{"text": "Appendix", "level": 1, "start": 900}], stack)

    assert [t for _, t in stack] == ["Appendix"]


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
