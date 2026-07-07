"""FastAPI application factory."""

import asyncio
import sys

# psycopg3 async is incompatible with Windows' ProactorEventLoop. Set the
# selector policy at import time so in-process runners (pytest TestClient,
# scripts) are safe. The `python -m pynote_api` entrypoint sets it earlier still.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager

from arq.connections import RedisSettings, create_pool
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from pynote_api.routes import chat, health, jobs, mindmap, notebooks, search, sources, summaries
from pynote_core.settings import get_settings
from pynote_core.tracing import configure_tracing


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    configure_tracing()
    # Create LangGraph checkpoint tables if missing. Idempotent.
    from pynote_core.chat_graph import setup_checkpoint_tables

    # Startup must not crash if DB is briefly unavailable.
    try:
        await setup_checkpoint_tables()
    except Exception:
        import logging

        logging.getLogger("pynote_api").exception(
            "Failed to set up LangGraph checkpoint tables; /chat will fail until DB is up."
        )

    # One compiled chat graph + checkpointer connection pool for the whole
    # process (RAG_ROADMAP 1.3). Routes fall back to a per-request graph if
    # this failed at boot (e.g. DB briefly down) — see chat._graph_for.
    from pynote_core.chat_graph import open_pooled_chat_graph

    graph_stack = AsyncExitStack()
    app.state.chat_graph = None
    try:
        app.state.chat_graph = await graph_stack.enter_async_context(open_pooled_chat_graph())
    except Exception:
        import logging

        logging.getLogger("pynote_api").exception(
            "Failed to open the shared chat graph pool; /chat will fall back per-request."
        )

    # One arq/Redis pool for the whole process, reused by every request that
    # enqueues a job (see deps.get_arq). Guarded so a briefly-down Redis at
    # boot doesn't crash startup — get_arq falls back to a transient pool.
    settings = get_settings()
    try:
        app.state.arq_pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    except Exception:
        import logging

        app.state.arq_pool = None
        logging.getLogger("pynote_api").exception(
            "Failed to create the shared arq pool at startup; will create per-request."
        )
    try:
        yield
    finally:
        pool = getattr(app.state, "arq_pool", None)
        if pool is not None:
            await pool.close()
        await graph_stack.aclose()


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="PyNote API",
        version="0.1.0",
        description="A NotebookLM-style RAG service.",
        lifespan=lifespan,
        openapi_url="/openapi.json" if settings.environment != "production" else None,
        docs_url="/docs" if settings.environment != "production" else None,
    )

    # CORS — the Next.js web app is on a different origin in dev.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router)
    app.include_router(notebooks.router, prefix="/api/v1")
    app.include_router(sources.router, prefix="/api/v1")
    app.include_router(search.router, prefix="/api/v1")
    app.include_router(chat.router, prefix="/api/v1")
    app.include_router(summaries.router, prefix="/api/v1")
    app.include_router(mindmap.router, prefix="/api/v1")
    app.include_router(jobs.router, prefix="/api/v1")

    return app


app = create_app()
