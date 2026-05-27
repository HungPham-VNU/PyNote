"""LangSmith initialization.

LangChain auto-traces every Runnable when these env vars are set;
this module just ensures they're exported from our typed Settings.
"""

import os

from pynote_core.settings import get_settings


def configure_tracing() -> bool:
    """Export LangSmith env vars from Settings. Returns True if tracing is enabled."""
    settings = get_settings()
    if not (settings.langsmith_tracing and settings.langsmith_api_key):
        os.environ["LANGSMITH_TRACING"] = "false"
        return False

    os.environ["LANGSMITH_TRACING"] = "true"
    os.environ["LANGSMITH_API_KEY"] = settings.langsmith_api_key
    os.environ["LANGSMITH_PROJECT"] = settings.langsmith_project
    os.environ["LANGSMITH_ENDPOINT"] = settings.langsmith_endpoint
    return True
