"""Chat endpoint (M4: LangGraph + AsyncPostgresSaver + SSE streaming).

POST /api/v1/notebooks/{notebook_id}/chat
  body: {"thread_id"?: UUID, "message": str, "selected_text"?: str}
  →    Server-Sent Events stream:
       event: start    data: {"thread_id": "..."}
       event: token    data: {"text": "..."}
       (... many token events ...)
       event: citations data: {"citations": [...]}
       event: done     data: {"thread_id": "...", "n_citations": N}

GET /api/v1/notebooks/{notebook_id}/threads/{thread_id}/history
  →    {"thread_id": ..., "messages": [{role, content, citations?}, ...]}
"""

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from pynote_api.auth import Principal
from pynote_api.deps import current_principal, get_db, load_owned_notebook
from pynote_core.chat_graph import open_chat_graph

router = APIRouter(tags=["chat"])


# ---- request / response shapes --------------------------------------------


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=8000)
    thread_id: UUID | None = None
    selected_text: str | None = Field(default=None, max_length=4000)


class HistoryMessage(BaseModel):
    role: str  # "user" | "assistant"
    content: str
    citations: list[dict[str, Any]] = Field(default_factory=list)


class HistoryResponse(BaseModel):
    thread_id: UUID
    messages: list[HistoryMessage]


# ---- helpers ---------------------------------------------------------------


async def _check_notebook(notebook_id: UUID, principal: Principal, db: AsyncSession) -> None:
    await load_owned_notebook(notebook_id, principal, db)


@asynccontextmanager
async def _graph_for(request: Request) -> AsyncIterator[Any]:
    """Yield the process-wide chat graph (opened in lifespan), or fall back to
    a per-request one when the shared pool failed at boot / in tests."""
    shared = getattr(request.app.state, "chat_graph", None)
    if shared is not None:
        yield shared
    else:
        async with open_chat_graph() as graph:
            yield graph


def _sse(event: str, data: dict[str, Any]) -> bytes:
    """Single SSE event in the canonical wire format."""
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n".encode()


def _last_message_text(content: Any) -> str:
    """Flatten a content block list to plain text for history display."""
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


# ---- POST /chat (SSE) ------------------------------------------------------


@router.post("/notebooks/{notebook_id}/chat")
async def chat(
    request: Request,
    notebook_id: UUID,
    body: ChatRequest,
    principal: Principal = Depends(current_principal),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    await _check_notebook(notebook_id, principal, db)

    thread_id = body.thread_id or uuid4()
    config = {"configurable": {"thread_id": str(thread_id)}}

    async def event_stream() -> AsyncIterator[bytes]:
        yield _sse("start", {"thread_id": str(thread_id)})

        try:
            async with _graph_for(request) as graph:
                state_input = {
                    "notebook_id": str(notebook_id),
                    "question": body.message,
                    "selected_text": body.selected_text,
                }

                # `stream_mode="messages"` yields (message_chunk, metadata) for every
                # LLM token. We forward only chunks from the `generate` node and
                # filter out tool/system noise.
                async for chunk, metadata in graph.astream(
                    state_input,
                    config=config,  # type: ignore[arg-type]
                    stream_mode="messages",
                ):
                    if metadata.get("langgraph_node") != "generate":
                        continue
                    if not isinstance(chunk, AIMessageChunk):
                        continue
                    text = _last_message_text(chunk.content)
                    if text:
                        yield _sse("token", {"text": text})

                # After streaming completes, read the final state for citations.
                final = await graph.aget_state(config)  # type: ignore[arg-type]
                citations = (final.values or {}).get("last_citations", [])
                yield _sse("citations", {"citations": citations})
                yield _sse(
                    "done",
                    {"thread_id": str(thread_id), "n_citations": len(citations)},
                )
        except Exception as e:
            yield _sse("error", {"message": str(e)[:500]})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # disable nginx buffering if proxied
        },
    )


# ---- GET /threads/{id}/history --------------------------------------------


@router.get(
    "/notebooks/{notebook_id}/threads/{thread_id}/history",
    response_model=HistoryResponse,
)
async def thread_history(
    request: Request,
    notebook_id: UUID,
    thread_id: UUID,
    principal: Principal = Depends(current_principal),
    db: AsyncSession = Depends(get_db),
) -> HistoryResponse:
    await _check_notebook(notebook_id, principal, db)

    config = {"configurable": {"thread_id": str(thread_id)}}
    async with _graph_for(request) as graph:
        state = await graph.aget_state(config)  # type: ignore[arg-type]

    values = state.values or {}
    messages_raw = values.get("messages") or []
    last_citations = values.get("last_citations") or []

    history: list[HistoryMessage] = []
    for i, m in enumerate(messages_raw):
        if isinstance(m, HumanMessage):
            history.append(
                HistoryMessage(role="user", content=_last_message_text(m.content)),
            )
        elif isinstance(m, AIMessage):
            # Per-message citations live on additional_kwargs (RAG_ROADMAP 2.1).
            # Threads persisted before that change only have `last_citations`
            # for the final turn — fall back so old threads don't regress.
            citations = m.additional_kwargs.get("citations")
            if citations is None and i == len(messages_raw) - 1:
                citations = last_citations
            history.append(
                HistoryMessage(
                    role="assistant",
                    content=_last_message_text(m.content),
                    citations=list(citations or []),
                )
            )

    return HistoryResponse(thread_id=thread_id, messages=history)
