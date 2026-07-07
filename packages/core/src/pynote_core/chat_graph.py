"""M4 chat graph.

Pipeline (RAG_ROADMAP.md Phase 1):

    rewrite → retrieve → pack → generate (streaming) → map_citations

- rewrite: condenses history + question into a standalone search query so
  follow-ups ("what about the second one?") retrieve correctly. Skipped on
  turn 1 without a selection; falls back to the raw question on any failure.
- retrieve: hybrid RRF + rerank on the rewritten query, then overlap-dedup.
- generate: trimmed history + Anthropic prompt caching (system + history
  prefix cached; per-turn search results stay uncached).
- map_citations: resolves citations AND persists them onto the AIMessage's
  additional_kwargs so history reloads keep per-message citations.

State is persisted by AsyncPostgresSaver keyed on `thread_id`, so reloading the
UI replays the same conversation. PostgresSaver creates its own checkpoint
tables on first `setup()` call — see `lifespan` in apps/api/main.py.

The graph itself does not stream; callers stream via `chat_graph.astream(...)`
with `stream_mode="messages"` to get token chunks from the generate node, then
read the final state for citations.
"""

from __future__ import annotations

import logging
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
from pynote_core.llm import _anthropic_kwargs, get_cheap_model
from pynote_core.retrieval import Hit, dedup_overlaps, hybrid_retrieve, rerank
from pynote_core.settings import get_settings

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from langgraph.graph.state import CompiledStateGraph

log = logging.getLogger("pynote_core.chat_graph")


# ---- state -----------------------------------------------------------------


class ChatState(TypedDict, total=False):
    """Conversation thread state.

    Persisted fields: `messages` (the conversation), `notebook_id`.
    Transient per-turn fields: question, selected_text, search_query, hits,
    citations. PostgresSaver checkpoints all of them; `map_citations` clears
    `hits` at end of turn so checkpoints don't carry chunk bodies.
    """

    # Persisted
    messages: Annotated[list[BaseMessage], add_messages]
    notebook_id: str

    # Transient (set fresh each turn)
    question: str
    selected_text: str | None
    search_query: str  # standalone query produced by the rewrite node
    hits: list[dict[str, Any]]  # JSON-shaped Hit; raw dataclasses don't checkpoint cleanly
    last_citations: list[dict[str, Any]]


SYSTEM_PROMPT = (
    "You are PyNote, a research assistant grounded in the user's notebook. "
    "Answer using ONLY the provided search results. Quote from them so the "
    "system can attach citations. If the answer isn't there, say so plainly."
)

# Model-input history budget: keep the tail of the conversation, starting on a
# user turn. Full history stays in checkpoints (the history endpoint needs it);
# this only bounds what we send to the model each turn.
MAX_HISTORY_MESSAGES = 12

# Rerank over-fetch so overlap-dedup can drop near-duplicates without
# shrinking the packed set below PACK_TOP_K.
RERANK_TOP_K = 12
PACK_TOP_K = 8


# ---- helpers ----------------------------------------------------------------


def _flatten_text(content: Any) -> str:
    """Flatten message content (str or block list) to plain text."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for b in content:
            if isinstance(b, dict) and b.get("type") == "text":
                parts.append(str(b.get("text", "")))
            elif isinstance(b, str):
                parts.append(b)
        return "".join(parts)
    return ""


def _trim_history(messages: list[BaseMessage], *, max_messages: int = MAX_HISTORY_MESSAGES) -> list[BaseMessage]:
    """Keep the most recent messages, aligned to start on a HumanMessage.

    Alignment matters: a window starting mid-turn (on an AIMessage) confuses
    the model and breaks prompt-cache prefix stability across turns.
    """
    if len(messages) <= max_messages:
        return list(messages)
    tail = messages[-max_messages:]
    for i, m in enumerate(tail):
        if isinstance(m, HumanMessage):
            return list(tail[i:])
    return list(tail)


def _with_cache_breakpoint(msg: BaseMessage) -> BaseMessage:
    """Return a copy of `msg` whose last content block carries cache_control.

    Only plain-string and dict-block contents are handled; anything else is
    returned unchanged (caching is an optimization, never a correctness risk).
    """
    content = msg.content
    if isinstance(content, str):
        blocks: list[Any] = [
            {"type": "text", "text": content, "cache_control": {"type": "ephemeral"}}
        ]
    elif isinstance(content, list) and content and isinstance(content[-1], dict):
        last = {**content[-1], "cache_control": {"type": "ephemeral"}}
        blocks = [*content[:-1], last]
    else:
        return msg
    return msg.model_copy(update={"content": blocks})


# ---- nodes -----------------------------------------------------------------


_REWRITE_PROMPT = (
    "Rewrite the user's latest question as a single standalone search query, "
    "resolving pronouns and references using the conversation. Keep every "
    "specific term (names, numbers, section titles) that helps retrieval. "
    "Return ONLY the query text, nothing else.\n\n"
    "{selection}Conversation:\n{history}\n\nLatest question: {question}"
)


async def node_rewrite(state: ChatState) -> dict[str, Any]:
    """Condense history + question into a standalone search query.

    Turn 1 without a selection: pass-through (no model call, no latency).
    Any model failure: fall back to the raw question — never block the turn.
    """
    question = state["question"]
    history = state.get("messages") or []
    selection = (state.get("selected_text") or "").strip()

    if not history and not selection:
        return {"search_query": question}

    transcript = "\n".join(
        f"{'user' if isinstance(m, HumanMessage) else 'assistant'}: "
        f"{_flatten_text(m.content)[:400]}"
        for m in history[-6:]
    )
    selection_part = (
        f"The user highlighted this passage (their question may refer to it):\n«{selection[:500]}»\n\n"
        if selection
        else ""
    )
    try:
        model = get_cheap_model()
        resp = await model.ainvoke(
            [
                HumanMessage(
                    content=_REWRITE_PROMPT.format(
                        selection=selection_part,
                        history=transcript or "(none)",
                        question=question,
                    )
                )
            ]
        )
        rewritten = _flatten_text(resp.content).strip().strip('"')
        if rewritten:
            return {"search_query": rewritten}
    except Exception as e:  # noqa: BLE001 — rewrite is best-effort by design
        log.warning("query rewrite failed, falling back to raw question: %s", e)
    return {"search_query": question}


async def node_retrieve(state: ChatState) -> dict[str, Any]:
    """Hybrid SQL + (optional) Voyage rerank + overlap dedup, on the rewritten query."""
    from uuid import UUID

    nb = UUID(state["notebook_id"])
    query = state.get("search_query") or state["question"]

    candidates = await hybrid_retrieve(nb, query, k=50)
    reranked = await rerank(query, candidates, top_k=RERANK_TOP_K)
    top = dedup_overlaps(reranked, top_k=PACK_TOP_K)

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
    """Call Claude with `search_result` blocks + trimmed, cache-marked history.

    Tokens stream via the model itself (LangGraph captures them when callers
    use `stream_mode="messages"`). The final AIMessage is what we return for
    state, with full content blocks so `map_citations` can read them.

    Prompt caching: breakpoints on the system prompt and the last Human
    message of prior history make the stable prefix cacheable; search results
    and the new question come after and stay uncached (they change per turn).
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

    history = _trim_history(state.get("messages") or [])
    # Cache breakpoint on the last prior *user* turn: Human history messages
    # are plain strings, so wrapping them is safe (AI messages carry citation
    # blocks we'd rather not mutate).
    for i in range(len(history) - 1, -1, -1):
        if isinstance(history[i], HumanMessage):
            history[i] = _with_cache_breakpoint(history[i])
            break

    messages: list[BaseMessage] = [
        _with_cache_breakpoint(SystemMessage(content=SYSTEM_PROMPT)),
        *history,
        HumanMessage(content=blocks),  # type: ignore[arg-type]  # dict-list content
    ]

    model = _build_chat_model()
    response = await model.ainvoke(messages)

    return {"messages": [HumanMessage(content=state["question"]), response]}


def node_map_citations(state: ChatState) -> dict[str, Any]:
    """Resolve Claude's char-location citations back to chunk identities.

    Also persists the resolved citations on the AIMessage itself
    (`additional_kwargs["citations"]`) — `add_messages` replaces a message
    with the same id, so the checkpointed history carries per-message
    citations and thread reloads keep them (RAG_ROADMAP 2.1). Clears `hits`
    so checkpoints don't snapshot chunk bodies (1.6).
    """
    messages = state.get("messages") or []
    if not messages:
        return {"last_citations": [], "hits": []}

    # The last assistant message holds the response content blocks.
    last = messages[-1]
    if not isinstance(last, AIMessage):
        return {"last_citations": [], "hits": []}

    hits = _hits_from_state(state)
    parsed = parse_response(last.content, hits)
    citations = [citation_to_jsonable(c) for c in parsed.citations]

    updated = last.model_copy(
        update={"additional_kwargs": {**last.additional_kwargs, "citations": citations}}
    )
    return {"messages": [updated], "last_citations": citations, "hits": []}


# ---- assembly --------------------------------------------------------------


def _build_chat_model() -> ChatAnthropic:
    """Citation-enabled Claude. Separate from `llm.get_chat_model` because we
    pass `search_result` content blocks ourselves and don't want the fallback.
    """
    settings = get_settings()
    return ChatAnthropic(  # type: ignore[call-arg]
        model=settings.anthropic_model_chat,
        **_anthropic_kwargs(settings),  # type: ignore[arg-type]
    )


def _build_graph() -> StateGraph[ChatState]:
    g = StateGraph(ChatState)
    g.add_node("rewrite", node_rewrite)
    g.add_node("retrieve", node_retrieve)
    g.add_node("generate", node_generate)
    g.add_node("map_citations", node_map_citations)
    g.add_edge(START, "rewrite")
    g.add_edge("rewrite", "retrieve")
    g.add_edge("retrieve", "generate")
    g.add_edge("generate", "map_citations")
    g.add_edge("map_citations", END)
    return g


@asynccontextmanager
async def open_chat_graph() -> AsyncIterator[CompiledStateGraph[ChatState]]:
    """Context manager that yields a compiled graph with PostgresSaver checkpointer.

    Opens its own connection; suitable for CLI/eval one-shots. The API holds a
    process-wide graph opened once in lifespan (see apps/api/main.py) instead
    of paying connection setup per request.

        async with open_chat_graph() as graph:
            async for evt in graph.astream(state, config=config):
                ...
    """
    settings = get_settings()
    sync_url = settings.database_url.replace("postgresql+psycopg://", "postgresql://", 1)
    async with AsyncPostgresSaver.from_conn_string(sync_url) as saver:
        graph = _build_graph().compile(checkpointer=saver)
        yield graph


@asynccontextmanager
async def open_pooled_chat_graph(
    *, max_size: int = 10
) -> AsyncIterator[CompiledStateGraph[ChatState]]:
    """Compiled graph backed by a psycopg AsyncConnectionPool.

    Enter ONCE per process (the API lifespan) and share the yielded graph
    across requests — unlike `open_chat_graph`, which pays connection setup on
    every entry. The pool makes concurrent checkpoint reads/writes safe.
    """
    from psycopg.rows import dict_row
    from psycopg_pool import AsyncConnectionPool

    settings = get_settings()
    sync_url = settings.database_url.replace("postgresql+psycopg://", "postgresql://", 1)
    pool: AsyncConnectionPool = AsyncConnectionPool(
        conninfo=sync_url,
        max_size=max_size,
        open=False,
        # Saver requirements: autocommit + dict_row; prepared statements off
        # because pgbouncer-style poolers choke on them.
        kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row},
    )
    await pool.open()
    try:
        saver = AsyncPostgresSaver(pool)  # type: ignore[arg-type]
        yield _build_graph().compile(checkpointer=saver)
    finally:
        await pool.close()


@lru_cache(maxsize=1)
def _graph_singleton() -> StateGraph[ChatState]:
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
