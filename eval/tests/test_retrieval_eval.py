"""Scoring-logic tests for eval/retrieval_eval.py — pure functions, no DB."""

from uuid import uuid4

from eval.retrieval_eval import _first_gold_rank, _matches, _stage_rankings, summarize
from pynote_core.retrieval import Hit


def _hit(text: str, *, page: int = 1, title: str = "Doc", dense=None, sparse=None) -> Hit:
    return Hit(
        chunk_id=uuid4(),
        source_id=uuid4(),
        source_part_id=uuid4(),
        source_title=title,
        page=page,
        text=text,
        char_start=0,
        char_end=len(text),
        score=1.0,
        score_dense=dense,
        score_sparse=sparse,
    )


def test_matches_normalizes_whitespace_and_case() -> None:
    h = _hit("The  Model\nachieved 12% improvement")
    assert _matches(h, {"must_contain": "the model achieved 12% improvement"})


def test_matches_respects_page_and_title() -> None:
    h = _hit("alpha beta", page=3, title="Paper A")
    assert _matches(h, {"must_contain": "alpha", "page": 3, "source_title": "Paper A"})
    assert not _matches(h, {"must_contain": "alpha", "page": 4})
    assert not _matches(h, {"must_contain": "alpha", "source_title": "Paper B"})


def test_matches_rejects_empty_needle() -> None:
    assert not _matches(_hit("anything"), {"must_contain": ""})


def test_first_gold_rank_is_one_based() -> None:
    hits = [_hit("miss"), _hit("the answer is here"), _hit("miss too")]
    assert _first_gold_rank(hits, [{"must_contain": "answer is here"}]) == 2
    assert _first_gold_rank(hits, [{"must_contain": "absent"}]) is None


def test_stage_rankings_orders_by_leg_score() -> None:
    a = _hit("a", dense=0.9, sparse=None)
    b = _hit("b", dense=0.5, sparse=0.8)
    c = _hit("c", dense=None, sparse=0.9)
    fused = [b, a, c]  # RRF order, deliberately different from leg orders
    r = _stage_rankings(fused, packed=[a])
    assert r["dense"] == [a, b]
    assert r["sparse"] == [c, b]
    assert r["hybrid"] == fused
    assert r["packed"] == [a]


def test_summarize_averages_and_counts_errors() -> None:
    rows = [
        {"error": None, "hybrid_rr": 1.0, "hybrid_recall@8": 1.0},
        {"error": None, "hybrid_rr": 0.5, "hybrid_recall@8": 1.0},
        {"error": "boom"},
    ]
    s = summarize(rows)
    assert s["n"] == 2
    assert s["n_errors"] == 1
    assert s["avg"]["hybrid_mrr"] == 0.75
    assert s["avg"]["hybrid_recall@8"] == 1.0
