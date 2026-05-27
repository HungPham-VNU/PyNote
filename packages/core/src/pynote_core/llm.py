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


def _anthropic_kwargs(settings: Settings) -> dict[str, object]:
    """Common kwargs for ChatAnthropic — works against direct API or GH Models proxy."""
    kw: dict[str, object] = {
        "api_key": settings.anthropic_api_key or "missing",
        "temperature": 0.2,
        "max_tokens": 4096,
    }
    if settings.anthropic_base_url:
        kw["base_url"] = settings.anthropic_base_url
    return kw


def _make_anthropic(model: str, settings: Settings) -> BaseChatModel:
    from langchain_anthropic import ChatAnthropic

    return ChatAnthropic(model=model, **_anthropic_kwargs(settings))  # type: ignore[arg-type]


def _make_gemini(model: str, settings: Settings) -> BaseChatModel:
    from langchain_google_genai import ChatGoogleGenerativeAI

    return ChatGoogleGenerativeAI(
        model=model,
        google_api_key=settings.google_api_key or "missing",
        temperature=0.2,
    )


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
        return _make_gemini(settings.gemini_model_heavy, settings)
    return _make_anthropic(settings.anthropic_model_heavy, settings)


def reset_model_cache() -> None:
    """Test hook — clears the lru_cache so settings changes take effect."""
    get_chat_model.cache_clear()
    get_cheap_model.cache_clear()
    get_heavy_model.cache_clear()
