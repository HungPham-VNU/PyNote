"""Application settings.

Single source of truth for runtime config. Loaded from environment
(see .env.example). Cached via lru_cache — call get_settings() everywhere.
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ---- Runtime mode ----
    provider_tier: Literal["free", "prod"] = "free"
    environment: Literal["development", "test", "production"] = "development"
    log_level: str = "info"

    # ---- Postgres ----
    database_url: str = Field(
        default="postgresql+psycopg://pynote:pynote_dev_password@localhost:5432/pynote",
    )

    # ---- Redis ----
    redis_url: str = "redis://localhost:6379/0"

    # ---- Object store (S3-compatible) ----
    s3_endpoint_url: str | None = "http://localhost:9000"
    s3_region: str = "auto"
    s3_access_key_id: str = "pynote"
    s3_secret_access_key: str = "pynote_dev_password"
    s3_bucket: str = "pynote-sources"
    s3_force_path_style: bool = True

    # ---- LLM: Anthropic (direct or via GitHub Models) ----
    anthropic_api_key: str | None = None
    anthropic_base_url: str = "https://models.inference.ai.azure.com"
    anthropic_model_chat: str = "claude-sonnet-4-6"
    anthropic_model_heavy: str = "claude-opus-4-7"

    # ---- LLM: Gemini (free-tier cheap ops) ----
    google_api_key: str | None = None
    gemini_model_cheap: str = "gemini-2.0-flash"
    gemini_model_heavy: str = "gemini-2.5-pro"

    # ---- Embeddings ----
    # Default in M2: bge-small-local via fastembed (~130MB ONNX, 384-dim, fast CPU).
    # Swap to bge-m3-local (~2GB, 1024-dim) or voyage (1024-dim) once schema migrated.
    embedding_provider: Literal["bge-small-local", "bge-m3-local", "voyage", "gemini"] = (
        "bge-small-local"
    )
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    embedding_dim: int = 384
    voyage_api_key: str | None = None

    # ---- Rerank ----
    rerank_provider: Literal["voyage", "bge-local"] = "voyage"
    rerank_model: str = "rerank-2.5"

    # ---- Clerk auth ----
    clerk_publishable_key: str | None = None
    clerk_secret_key: str | None = None
    clerk_jwks_url: str | None = None

    # ---- LangSmith ----
    langsmith_tracing: bool = True
    langsmith_api_key: str | None = None
    langsmith_project: str = "pynote-dev"
    langsmith_endpoint: str = "https://api.smith.langchain.com"

    # ---- Worker ----
    worker_concurrency: int = 4


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Process-wide cached settings."""
    return Settings()
