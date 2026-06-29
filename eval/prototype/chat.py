"""Single Anthropic chat turn with retrieval + citations.

This is the shape of the M4 chat-graph `generate` node, distilled to a single
function so the prototype CLI can exercise it without LangGraph.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from eval.prototype.citations import ParsedAnswer, pack_search_results, parse_response
from eval.prototype.retrieval import hybrid_retrieve, rerank
from pynote_core.llm import get_chat_model

if TYPE_CHECKING:
    from uuid import UUID

    from eval.prototype.retrieval import Hit

SYSTEM_PROMPT = (
    "You are PyNote, a research assistant. Answer the user's question using "
    "ONLY the provided search results. Cite every factual claim by quoting "
    "from a search result — the system will attach citations automatically. "
    "If the search results do not contain the answer, say so plainly."
)


async def ask(
    notebook_id: UUID,
    question: str,
    *,
    history: list[dict[str, Any]] | None = None,
    selection: str | None = None,
    candidate_k: int = 50,
    top_k: int = 8,
) -> tuple[ParsedAnswer, list[Hit]]:
    """Retrieve → rerank → call Claude with search_result blocks → parse citations.

    Returns the parsed answer and the hits that were packed (in pack order,
    so `hits[citation.search_result_index]` is well-defined).
    """
    # When the user has selected text, bias retrieval toward that context.
    query_for_retrieval = f"{selection}\n\n{question}" if selection else question
    candidates = await hybrid_retrieve(notebook_id, query_for_retrieval, k=candidate_k)
    hits = await rerank(question, candidates, top_k=top_k)

    user_content: list[dict[str, Any]] = pack_search_results(hits)
    if selection:
        user_content.append(
            {
                "type": "text",
                "text": (
                    "The user highlighted this passage in a source. Treat it as "
                    f"the focus of their question:\n\n«{selection}»\n\n"
                ),
            }
        )
    user_content.append({"type": "text", "text": question})

    messages: list[dict[str, Any]] = [{"role": "system", "content": SYSTEM_PROMPT}]
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": user_content})

    model = get_chat_model()
    response = await model.ainvoke(messages)

    return parse_response(response.content, hits), hits
