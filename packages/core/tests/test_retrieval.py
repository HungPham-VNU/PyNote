"""Pure-function retrieval tests — no DB, no embedder.

`dedup_overlaps` guards the search_result packing budget: overlapping chunks
from the 200-char chunker overlap must not occupy multiple slots.
"""

from uuid import uuid4

from pynote_core.retrieval import Hit, dedup_overlaps


def _hit(part_id, start: int, end: int, score: float) -> Hit:
    return Hit(
        chunk_id=uuid4(),
        source_id=uuid4(),
        source_part_id=part_id,
        source_title="t",
        page=1,
        text="x" * (end - start),
        char_start=start,
        char_end=end,
        score=score,
    )


def test_dedup_drops_overlapping_same_part() -> None:
    part = uuid4()
    best = _hit(part, 0, 1200, 0.9)
    overlapping = _hit(part, 1000, 2200, 0.8)  # overlaps [1000, 1200)
    disjoint = _hit(part, 2200, 3400, 0.7)
    out = dedup_overlaps([best, overlapping, disjoint], top_k=8)
    assert out == [best, disjoint]


def test_dedup_keeps_same_range_different_parts() -> None:
    a = _hit(uuid4(), 0, 1200, 0.9)
    b = _hit(uuid4(), 0, 1200, 0.8)
    assert dedup_overlaps([a, b], top_k=8) == [a, b]


def test_dedup_respects_top_k() -> None:
    part = uuid4()
    hits = [_hit(part, i * 2000, i * 2000 + 1200, 1.0 - i * 0.1) for i in range(6)]
    assert len(dedup_overlaps(hits, top_k=3)) == 3


def test_dedup_empty() -> None:
    assert dedup_overlaps([], top_k=8) == []


def test_dedup_touching_ranges_are_not_overlapping() -> None:
    part = uuid4()
    a = _hit(part, 0, 1200, 0.9)
    b = _hit(part, 1200, 2400, 0.8)  # starts exactly where a ends
    assert dedup_overlaps([a, b], top_k=8) == [a, b]
