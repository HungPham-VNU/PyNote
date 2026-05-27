"""Programmatic uvicorn entrypoint.

Why this exists: psycopg3's async mode cannot run on asyncio's
ProactorEventLoop, which is uvicorn's default on Windows. We must install the
SelectorEventLoop policy *before* the event loop is created — that is impossible
to do reliably when the app is imported by the `uvicorn ...` CLI (the loop is
already running by then). Running through this module fixes it.

Run:
    python -m pynote_api            # or: just api

Env:
    API_HOST   (default 127.0.0.1)
    API_PORT   (default 8000)
    API_RELOAD (default: 0 on Windows, 1 elsewhere)
                Note: hot-reload on Windows spawns worker subprocesses that
                re-create a ProactorEventLoop, so DB calls break under reload.
                Keep it off on Windows, or set API_RELOAD=1 and accept manual
                restarts for DB-touching endpoints.
"""

import asyncio
import os
import sys


def main() -> None:
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    import uvicorn

    default_reload = "0" if sys.platform == "win32" else "1"
    reload = os.environ.get("API_RELOAD", default_reload) == "1"

    uvicorn.run(
        "pynote_api.main:app",
        host=os.environ.get("API_HOST", "127.0.0.1"),
        port=int(os.environ.get("API_PORT", "8000")),
        reload=reload,
    )


if __name__ == "__main__":
    main()
