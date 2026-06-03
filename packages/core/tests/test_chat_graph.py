"""Chat-graph wiring tests — pure-graph shape, no LLM, no DB.

The graph is constructed lazily by `_build_graph`; we assert the node names,
the edges, and the state schema so a future refactor that drops a node from
the pipeline fails loudly.
"""

from pynote_core.chat_graph import ChatState, _build_graph


def test_graph_has_expected_nodes() -> None:
    g = _build_graph()
    # StateGraph exposes its node names via `g.nodes`.
    assert {"retrieve", "generate", "map_citations"}.issubset(set(g.nodes))


def test_state_schema_includes_messages_and_notebook() -> None:
    # ChatState is a TypedDict; we check it advertises both persisted fields.
    keys = set(ChatState.__annotations__.keys())
    assert "messages" in keys
    assert "notebook_id" in keys
    assert "last_citations" in keys


def test_graph_compiles_without_checkpointer() -> None:
    """Even without PostgresSaver, the graph should compile cleanly.

    This catches schema/edge errors that would otherwise only surface at
    request time inside the SSE handler.
    """
    compiled = _build_graph().compile()
    assert compiled is not None
