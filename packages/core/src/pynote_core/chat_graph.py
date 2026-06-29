"""M4 chat graph.

Pipeline (clean version for v1; classify/rewrite land later if we measure latency wins):

    retrieve  → pack  → generate (streaming)  → map_citations

State is persisted by AsyncPostgresSaver keyed on `thread_id`, so reloading the
UI replays the same conversation. PostgresSaver creates its own checkpoint
tables on first `setup()` call — see `lifespan` in apps/api/main.py.

The graph itself does not stream; callers stream via `chat_graph.astream(...)`
with `stream_mode="messages"` to get token chunks from the generate node, then
read the final state for citations.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from functools import lru_cache
from typing import TYPE_CHECKING, Annotated, Any, TypedDict

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages

from pynote_core.citations import (
    citation_to_jsonable,
    pack_search_results,
    parse_response,
)
from pynote_core.llm import _anthropic_kwargs
from pynote_core.retrieval import Hit, hybrid_retrieve, rerank
from pynote_core.settings import get_settings

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from langgraph.graph.state import CompiledStateGraph


# ---- state -----------------------------------------------------------------


class ChatState(TypedDict, total=False):
    """Conversation thread state.

    Persisted fields: `messages` (the conversation), `notebook_id`.
    Transient per-turn fields: question, selected_text, hits, citations.
    PostgresSaver checkpoints all of them, but transients overwrite each turn.
    """

    # Persisted
    messages: Annotated[list[BaseMessage], add_messages]
    notebook_id: str

    # Transient (set fresh each turn)
    question: str
    selected_text: str | None
    hits: list[dict[str, Any]]  # JSON-shaped Hit; raw dataclasses don't checkpoint cleanly
    last_citations: list[dict[str, Any]]


SYSTEM_PROMPT = (
    "You are PyNote, a research assistant grounded in the user's notebook. "
    "Answer using ONLY the provided search results. Quote from them so the "
    "system can attach citations. If the answer isn't there, say so plainly."
)


# ---- nodes -----------------------------------------------------------------


async def node_retrieve(state: ChatState) -> dict[str, Any]:
    """Run hybrid SQL + (optional) Voyage rerank. Output: top-K hits as dicts."""
    from uuid import UUID

    nb = UUID(state["notebook_id"])
    selection = state.get("selected_text") or ""
    query = f"{selection}\n\n{state['question']}" if selection else state["question"]

    candidates = await hybrid_retrieve(nb, query, k=50)
    top = await rerank(state["question"], candidates, top_k=8)

    # PostgresSaver serializes via msgpack; dataclasses come through but UUIDs don't.
    # Convert hits to plain dicts now so we can re-pack them for Claude later.
    hits_jsonable = [
        {
            "chunk_id": str(h.chunk_id),
            "source_id": str(h.source_id),
            "source_part_id": str(h.source_part_id),
            "source_title": h.source_title,
            "page": h.page,
            "text": h.text,
            "char_start": h.char_start,
            "char_end": h.char_end,
            "score": h.score,
        }
        for h in top
    ]
    return {"hits": hits_jsonable}


def _hits_from_state(state: ChatState) -> list[Hit]:
    """Rebuild typed Hits from the JSONable list in state."""
    from uuid import UUID

    out: list[Hit] = []
    for h in state.get("hits") or []:
        out.append(
            Hit(
                chunk_id=UUID(h["chunk_id"]),
                source_id=UUID(h["source_id"]),
                source_part_id=UUID(h["source_part_id"]),
                source_title=h.get("source_title"),
                page=h.get("page"),
                text=h["text"],
                char_start=h["char_start"],
                char_end=h["char_end"],
                score=float(h["score"]),
            )
        )
    return out


async def node_generate(state: ChatState) -> dict[str, Any]:
    """Call Claude with `search_result` blocks + history.

    Tokens stream via the model itself (LangGraph captures them when callers
    use `stream_mode="messages"`). The final AIMessage is what we return for
    state, with full content blocks so `map_citations` can read them.
    """
    hits = _hits_from_state(state)
    blocks: list[dict[str, Any]] = pack_search_results(hits)

    if state.get("selected_text"):
        blocks.append(
            {
                "type": "text",
                "text": (
                    "The user highlighted this passage. Treat it as the focus of "
                    f"their question:\n\n«{state['selected_text']}»\n\n"
                ),
            }
        )
    blocks.append({"type": "text", "text": state["question"]})

    messages: list[BaseMessage] = [
        SystemMessage(content=SYSTEM_PROMPT),
        *(state.get("messages") or []),
        HumanMessage(content=blocks),  # type: ignore[arg-type] — dict-list content
    ]

    model = _build_chat_model()
    response = await model.ainvoke(messages)

    return {"messages": [HumanMessage(content=state["question"]), response]}


def node_map_citations(state: ChatState) -> dict[str, Any]:
    """Resolve Claude's char-location citations back to chunk identities."""
    messages = state.get("messages") or []
    if not messages:
        return {"last_citations": []}

    # The last assistant message holds the response content blocks.
    last = messages[-1]
    if not isinstance(last, AIMessage):
        return {"last_citations": []}

    hits = _hits_from_state(state)
    parsed = parse_response(last.content, hits)
    return {"last_citations": [citation_to_jsonable(c) for c in parsed.citations]}


# ---- assembly --------------------------------------------------------------


def _build_chat_model() -> ChatAnthropic:
    """Citation-enabled Claude. Separate from `llm.get_chat_model` because we
    pass `search_result` content blocks ourselves and don't want the fallback.
    """
    settings = get_settings()
    return ChatAnthropic(
        model=settings.anthropic_model_chat,
        **_anthropic_kwargs(settings),  # type: ignore[arg-type]
    )


def _build_graph() -> StateGraph:
    g = StateGraph(ChatState)
    g.add_node("retrieve", node_retrieve)
    g.add_node("generate", node_generate)
    g.add_node("map_citations", node_map_citations)
    g.add_edge(START, "retrieve")
    g.add_edge("retrieve", "generate")
    g.add_edge("generate", "map_citations")
    g.add_edge("map_citations", END)
    return g


@asynccontextmanager
async def open_chat_graph() -> AsyncIterator[CompiledStateGraph]:
    """Context manager that yields a compiled graph with PostgresSaver checkpointer.

    The saver opens a connection pool; we close it on exit. Use:

        async with open_chat_graph() as graph:
            async for evt in graph.astream(state, config=config):
                ...
    """
    settings = get_settings()
    sync_url = settings.database_url.replace("postgresql+psycopg://", "postgresql://", 1)
    async with AsyncPostgresSaver.from_conn_string(sync_url) as saver:
        graph = _build_graph().compile(checkpointer=saver)
        yield graph


@lru_cache(maxsize=1)
def _graph_singleton() -> StateGraph:
    """Uncompiled graph singleton — useful for static inspection / tests."""
    return _build_graph()


async def setup_checkpoint_tables() -> None:
    """Create the LangGraph checkpoint tables. Idempotent.

    Call once at API startup (lifespan). The Saver creates `checkpoints`,
    `checkpoint_writes`, `checkpoint_blobs` in the public schema.
    """
    settings = get_settings()
    sync_url = settings.database_url.replace("postgresql+psycopg://", "postgresql://", 1)
    async with AsyncPostgresSaver.from_conn_string(sync_url) as saver:
        await saver.setup()
