"""LLM factory.

Switches providers based on PROVIDER_TIER. The rest of the app calls
`get_chat_model()` / `get_cheap_model()` / `get_heavy_model()` and stays
provider-agnostic.

Free path (default): Claude Sonnet via GitHub Models, with Gemini fallback.
Prod path: Claude direct (api.anthropic.com).

All factories return LangChain `BaseChatModel`s so downstream code is uniform.
"""

from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING

from pynote_core.settings import Settings, get_settings

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel


# Artifact generation (mind maps, study guides) emits large structured outputs —
# a 100-node mind map's tool-call JSON alone can run past 10k tokens. When the
# Anthropic API hits max_tokens mid tool-use block, the tool input comes back as
# an empty `{}`, which then fails Pydantic validation downstream ("nodes Field
# required, input_value={}"). 16k is the safe ceiling for non-streaming requests.
HEAVY_MAX_TOKENS = 16_000


def _anthropic_kwargs(settings: Settings, max_tokens: int = 4096) -> dict[str, object]:
    """Common kwargs for ChatAnthropic — works against direct API or GH Models proxy.

    `temperature` is intentionally omitted: Anthropic deprecated it for Opus 4+
    reasoning models (returns 400 `temperature is deprecated for this model`).
    Sonnet/Haiku still accept it but defaulting it costs us nothing.
    """
    kw: dict[str, object] = {
        "api_key": settings.anthropic_api_key or "missing",
        "max_tokens": max_tokens,
    }
    if settings.anthropic_base_url:
        kw["base_url"] = settings.anthropic_base_url
    return kw


def _make_anthropic(model: str, settings: Settings, max_tokens: int = 4096) -> BaseChatModel:
    from langchain_anthropic import ChatAnthropic

    return ChatAnthropic(model=model, **_anthropic_kwargs(settings, max_tokens))  # type: ignore[call-arg, arg-type]


def _make_gemini(
    model: str,
    settings: Settings,
    *,
    max_output_tokens: int | None = None,
    thinking_budget: int | None = None,
) -> BaseChatModel:
    from langchain_google_genai import ChatGoogleGenerativeAI

    # Gemini 2.5 models "think" by default, spending output tokens on hidden
    # reasoning. For large structured-output jobs (summary/mind map) that
    # reasoning competes with the JSON inside the output budget and truncates
    # it mid-token → OutputParserException. Callers that emit big JSON pass a
    # generous `max_output_tokens` and `thinking_budget=0` to prevent this.
    kwargs: dict[str, object] = {
        "model": model,
        "google_api_key": settings.google_api_key or "missing",
        "temperature": 0.2,
    }
    if max_output_tokens is not None:
        kwargs["max_output_tokens"] = max_output_tokens
    if thinking_budget is not None:
        kwargs["thinking_budget"] = thinking_budget
    return ChatGoogleGenerativeAI(**kwargs)


@lru_cache(maxsize=4)
def get_chat_model() -> BaseChatModel:
    """Primary chat model — citation-critical. Used for the grounded chat node."""
    settings = get_settings()
    primary = _make_anthropic(settings.anthropic_model_chat, settings)
    if settings.google_api_key:
        # Graceful fallback if GH Models rate-limits or 5xx's.
        fallback = _make_gemini(settings.gemini_model_cheap, settings)
        return primary.with_fallbacks([fallback])  # type: ignore[return-value]
    return primary


@lru_cache(maxsize=4)
def get_cheap_model() -> BaseChatModel:
    """For classifier / rewriter / outline workers.

    Free tier prefers Gemini Flash (1500 RPD) so we don't burn the Claude RPM
    budget on cheap ops.
    """
    settings = get_settings()
    if settings.provider_tier == "free" and settings.google_api_key:
        return _make_gemini(settings.gemini_model_cheap, settings)
    # Prod or no Gemini key: use Anthropic Haiku.
    return _make_anthropic("claude-haiku-4-5", settings)


@lru_cache(maxsize=4)
def get_heavy_model() -> BaseChatModel:
    """For artifact generation (study guides, mind maps, audio scripts)."""
    settings = get_settings()
    if settings.provider_tier == "free" and settings.google_api_key:
        return _make_gemini(
            settings.gemini_model_heavy,
            settings,
            max_output_tokens=HEAVY_MAX_TOKENS,
            thinking_budget=0,
        )
    return _make_anthropic(settings.anthropic_model_heavy, settings, max_tokens=HEAVY_MAX_TOKENS)


def reset_model_cache() -> None:
    """Test hook — clears the lru_cache so settings changes take effect."""
    get_chat_model.cache_clear()
    get_cheap_model.cache_clear()
    get_heavy_model.cache_clear()
