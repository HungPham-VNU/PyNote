"""Chat-graph wiring tests — pure-graph shape, no LLM, no DB.

The graph is constructed lazily by `_build_graph`; we assert the node names,
the edges, and the state schema so a future refactor that drops a node from
the pipeline fails loudly.
"""

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from pynote_core.chat_graph import (
    ChatState,
    _build_graph,
    _trim_history,
    _with_cache_breakpoint,
)


def test_graph_has_expected_nodes() -> None:
    g = _build_graph()
    # StateGraph exposes its node names via `g.nodes`.
    assert {"rewrite", "retrieve", "generate", "map_citations"}.issubset(set(g.nodes))


def test_state_schema_includes_messages_and_notebook() -> None:
    # ChatState is a TypedDict; we check it advertises both persisted fields.
    keys = set(ChatState.__annotations__.keys())
    assert "messages" in keys
    assert "notebook_id" in keys
    assert "last_citations" in keys
    assert "search_query" in keys


def test_trim_history_short_passthrough() -> None:
    msgs = [HumanMessage(content="q1"), AIMessage(content="a1")]
    assert _trim_history(msgs, max_messages=12) == msgs


def test_trim_history_starts_on_human_turn() -> None:
    msgs = []
    for i in range(10):
        msgs.append(HumanMessage(content=f"q{i}"))
        msgs.append(AIMessage(content=f"a{i}"))
    trimmed = _trim_history(msgs, max_messages=5)
    # 5-message tail is [a7, q8, a8, q9, a9] → aligned to start at q8.
    assert isinstance(trimmed[0], HumanMessage)
    assert trimmed[0].content == "q8"
    assert len(trimmed) == 4


def test_cache_breakpoint_wraps_string_content() -> None:
    msg = _with_cache_breakpoint(SystemMessage(content="rules"))
    assert isinstance(msg.content, list)
    assert msg.content[-1]["cache_control"] == {"type": "ephemeral"}
    assert msg.content[-1]["text"] == "rules"


def test_cache_breakpoint_marks_last_block_only() -> None:
    msg = _with_cache_breakpoint(
        HumanMessage(content=[{"type": "text", "text": "a"}, {"type": "text", "text": "b"}])
    )
    assert "cache_control" not in msg.content[0]
    assert msg.content[1]["cache_control"] == {"type": "ephemeral"}


def test_cache_breakpoint_leaves_original_untouched() -> None:
    original = HumanMessage(content=[{"type": "text", "text": "a"}])
    _with_cache_breakpoint(original)
    assert "cache_control" not in original.content[0]


def test_graph_compiles_without_checkpointer() -> None:
    """Even without PostgresSaver, the graph should compile cleanly.

    This catches schema/edge errors that would otherwise only surface at
    request time inside the SSE handler.
    """
    compiled = _build_graph().compile()
    assert compiled is not None
