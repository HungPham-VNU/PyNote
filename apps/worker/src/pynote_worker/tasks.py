"""arq task functions.

M0 surface: noop_task and ping_llm_task. M1 adds parse_source; M2 adds
embed_source; etc. Each task is also persisted in the `job` table so the
api can surface progress to the UI.
"""

from datetime import UTC, datetime
from typing import Any

from langchain_core.messages import HumanMessage

from pynote_core.llm import get_chat_model


async def noop_task(ctx: dict[str, Any]) -> dict[str, Any]:
    """Used by tests to confirm the worker is alive."""
    return {"ok": True, "at": datetime.now(UTC).isoformat()}


async def ping_llm_task(ctx: dict[str, Any], prompt: str = "ping") -> dict[str, Any]:
    """End-to-end smoke: routes through the configured chat model and traces to LangSmith."""
    model = get_chat_model()
    resp = await model.ainvoke([HumanMessage(content=prompt)])
    return {"ok": True, "reply": str(resp.content)[:500]}
