"""Programmatic uvicorn entrypoint.

Why this exists: psycopg3's async mode cannot run on asyncio's
ProactorEventLoop, which is Windows' default. We must (a) install the
SelectorEventLoop policy before *any* loop is created, and (b) stop uvicorn
from re-setting the policy in its own startup path. We do both by:

  1. Setting WindowsSelectorEventLoopPolicy at process start.
  2. Building uvicorn.Config with loop="none" so uvicorn does not touch
     the policy in setup_event_loop().
  3. Calling Server.serve() through asyncio.run(), which honors our policy.

This bypasses uvicorn.run() / Server.run() entirely on Windows.

Run:
    python -m pynote_api            # or: just api

Env:
    API_HOST   (default 127.0.0.1)
    API_PORT   (default 8000)
    API_RELOAD (default 0 on Windows, 1 elsewhere)
                Note: reload spawns worker subprocesses that re-create a
                ProactorEventLoop on Windows, breaking DB calls. Keep off
                on Windows or restart manually after edits.
"""

import asyncio
import os
import sys


def main() -> None:
    is_windows = sys.platform == "win32"
    if is_windows:
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    import uvicorn

    default_reload = "0" if is_windows else "1"
    reload = os.environ.get("API_RELOAD", default_reload) == "1"
    host = os.environ.get("API_HOST", "127.0.0.1")
    port = int(os.environ.get("API_PORT", "8000"))

    if is_windows and not reload:
        # Single-process Windows path: own the loop ourselves so uvicorn cannot
        # reset the policy back to Proactor.
        config = uvicorn.Config(
            "pynote_api.main:app",
            host=host,
            port=port,
            loop="none",   # tell uvicorn: do NOT call asyncio_setup
            reload=False,
            log_level=os.environ.get("LOG_LEVEL", "info").lower(),
        )
        server = uvicorn.Server(config)
        asyncio.run(server.serve())
        return

    # Linux / macOS, or Windows-with-reload (caller accepts the consequences).
    uvicorn.run(
        "pynote_api.main:app",
        host=host,
        port=port,
        reload=reload,
    )


if __name__ == "__main__":
    main()
