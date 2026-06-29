"""Pure-function tests for the eval metrics."""

from uuid import UUID

from eval.metrics import (
    ANSWER_RELEVANCY_LITE_GATE,
    CITATION_GROUNDING_GATE,
    FAITHFULNESS_LITE_GATE,
    aggregate,
    citation_grounding,
    lite_scores,
)
from pynote_core.citations import ParsedAnswer, ResolvedCitation


def _c(roundtrip_ok: bool, cited: str = "x") -> ResolvedCitation:
    return ResolvedCitation(
        cited_text=cited,
        search_result_index=0,
        start_char_index=0,
        end_char_index=len(cited),
        chunk_id=UUID(int=1),
        source_id=UUID(int=2),
        source_part_id=UUID(int=3),
        source_title="t",
        page=1,
        chunk_text_slice=cited if roundtrip_ok else cited + "drift",
        roundtrip_ok=roundtrip_ok,
    )


# ---- citation_grounding ----------------------------------------------------


def test_citation_grounding_no_citations_is_perfect() -> None:
    answer = ParsedAnswer(text="No claims here.", citations=[])
    assert citation_grounding(answer) == 1.0


def test_citation_grounding_fraction() -> None:
    answer = ParsedAnswer(text="...", citations=[_c(True), _c(True), _c(False)])
    assert abs(citation_grounding(answer) - 2 / 3) < 1e-9


# ---- lite_scores -----------------------------------------------------------


def test_lite_faithfulness_perfect_when_answer_subset_of_contexts() -> None:
    s = lite_scores(
        question="What is X?",
        contexts=["X is the answer to everything."],
        answer_text="X is the answer.",
        cited_texts=["X is the answer"],
    )
    assert s.faithfulness == 1.0
    # Question and answer share "x" and "the"
    assert s.answer_relevancy > 0.0
    assert s.grounding_overlap == 1.0


def test_lite_faithfulness_drops_when_answer_invents_tokens() -> None:
    s = lite_scores(
        question="What is X?",
        contexts=["X is the answer."],
        answer_text="X involves quantum entanglement.",
        cited_texts=[],
    )
    # "quantum" and "entanglement" are not in the contexts.
    assert s.faithfulness < 1.0


def test_lite_grounding_overlap_zero_when_cited_text_missing_from_contexts() -> None:
    s = lite_scores(
        question="?",
        contexts=["The cat sat."],
        answer_text="The cat sat.",
        cited_texts=["a dog barked"],
    )
    assert s.grounding_overlap == 0.0


def test_lite_empty_question_yields_zero_relevancy() -> None:
    s = lite_scores(question="", contexts=["x"], answer_text="x", cited_texts=[])
    assert s.answer_relevancy == 0.0


# ---- aggregate / gate ------------------------------------------------------


def test_aggregate_passes_when_all_gates_met() -> None:
    rows = [
        {
            "citation_grounding": CITATION_GROUNDING_GATE,
            "faithfulness_lite": FAITHFULNESS_LITE_GATE,
            "answer_relevancy_lite": ANSWER_RELEVANCY_LITE_GATE,
        },
        {
            "citation_grounding": 1.0,
            "faithfulness_lite": 1.0,
            "answer_relevancy_lite": 1.0,
        },
    ]
    gate = aggregate(rows)
    assert gate.n == 2
    assert gate.passed is True


def test_aggregate_fails_on_citation_grounding_dip() -> None:
    rows = [
        {
            "citation_grounding": 0.5,
            "faithfulness_lite": 1.0,
            "answer_relevancy_lite": 1.0,
        }
    ]
    gate = aggregate(rows)
    assert gate.passed is False


def test_aggregate_empty_fails_gracefully() -> None:
    gate = aggregate([])
    assert gate.n == 0
    assert gate.passed is False
