"""FastAPI application factory."""

import asyncio
import sys

# psycopg3 async is incompatible with Windows' ProactorEventLoop. Set the
# selector policy at import time so in-process runners (pytest TestClient,
# scripts) are safe. The `python -m pynote_api` entrypoint sets it earlier still.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from pynote_api.routes import health, jobs, notebooks, search, sources
from pynote_core.settings import get_settings
from pynote_core.tracing import configure_tracing


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    configure_tracing()
    yield


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
    app.include_router(jobs.router, prefix="/api/v1")

    return app


app = create_app()
