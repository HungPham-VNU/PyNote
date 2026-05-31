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

# Force-clear Clerk config so tests use dev-header auth regardless of what's in
# the developer's .env. Use a hard set (not setdefault) so a developer who has
# CLERK_JWKS_URL populated locally still gets predictable test behavior.
os.environ["CLERK_JWKS_URL"] = ""
os.environ["CLERK_PUBLISHABLE_KEY"] = ""
os.environ["CLERK_SECRET_KEY"] = ""
