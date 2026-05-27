"""Repo-wide pytest setup — runs before any test files are collected."""

import os

# Test defaults: never hit real services unless explicitly opted in.
os.environ.setdefault("PROVIDER_TIER", "free")
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("LANGSMITH_TRACING", "false")
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+psycopg://pynote:pynote_dev_password@localhost:5432/pynote_test",
)
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/1")
