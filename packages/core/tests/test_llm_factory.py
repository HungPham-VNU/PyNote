"""LLM factory smoke tests.

`test_smoke_chat_ping` is gated on a real ANTHROPIC_API_KEY being set
(GitHub Models token or Anthropic Console). Skips otherwise so CI is green
without secrets.
"""

import os

import pytest

from pynote_core.llm import get_chat_model, get_cheap_model, reset_model_cache


def setup_function() -> None:
    reset_model_cache()


def test_chat_model_constructs_without_keys() -> None:
    # No real API call — just verify the factory does not blow up.
    model = get_chat_model()
    assert model is not None


def test_cheap_model_constructs_without_keys() -> None:
    model = get_cheap_model()
    assert model is not None


@pytest.mark.skipif(
    not os.environ.get("ANTHROPIC_API_KEY"),
    reason="Set ANTHROPIC_API_KEY (GH Models token or Console key) to run smoke test.",
)
@pytest.mark.asyncio
async def test_smoke_chat_ping() -> None:
    """End-to-end: invoke the chat model with a one-word prompt."""
    from langchain_core.messages import HumanMessage

    model = get_chat_model()
    resp = await model.ainvoke([HumanMessage(content="Reply with exactly: pong")])
    assert "pong" in str(resp.content).lower()
