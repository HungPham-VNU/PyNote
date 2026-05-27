"""Verify settings load from env with sensible defaults."""

from pynote_core.settings import Settings


def test_defaults_under_free_tier() -> None:
    s = Settings()
    assert s.provider_tier == "free"
    assert s.anthropic_model_chat.startswith("claude-")
    assert s.embedding_provider == "bge-m3-local"
    assert s.rerank_model == "rerank-2.5"


def test_database_url_present() -> None:
    s = Settings()
    assert "postgresql" in s.database_url
