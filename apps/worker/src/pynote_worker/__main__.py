"""Worker entrypoint that installs the Windows SelectorEventLoop policy.

Same Windows issue as the API: psycopg3 async cannot run on a ProactorEventLoop.
The arq CLI (`arq pynote_worker.main.WorkerSettings`) does not give us a hook
to set the policy before its loop is created. This module does it explicitly,
then hands off to arq.

Run:
    python -m pynote_worker            # or: just worker
"""

import asyncio
import logging
import os
import sys
import threading


def _start_health_server() -> None:
    """Bind a throwaway HTTP health port in a daemon thread.

    Render's free tier only offers *web* services (background workers are paid),
    and a web service that doesn't bind `$PORT` gets killed at boot. arq itself
    listens on nothing, so we serve a trivial 200-on-any-path here purely to
    satisfy the platform health check (DEPLOY.md §2.3). No-op locally beyond
    holding a socket. If `$PORT` is unset (local `just worker`), we still bind
    a default so behavior is identical everywhere.
    """
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    port = int(os.environ.get("PORT", "8080"))

    class _Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 - stdlib naming
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"ok")

        def log_message(self, *_args: object) -> None:
            pass  # silence per-request stderr spam; arq owns the logs

    def _serve() -> None:
        try:
            ThreadingHTTPServer(("0.0.0.0", port), _Handler).serve_forever()
        except OSError:
            # Port already taken (e.g. two starts in one process) — the worker
            # is what matters, so log and carry on rather than crash.
            logging.getLogger("pynote_worker").warning(
                "health port %d unavailable; continuing without it", port
            )

    threading.Thread(target=_serve, name="health", daemon=True).start()
    logging.getLogger("pynote_worker").info("health server listening on :%d", port)


def _configure_logging() -> None:
    """arq's CLI sets this up for us; we bypass the CLI, so we do it here."""
    level = getattr(logging, os.environ.get("LOG_LEVEL", "INFO").upper(), logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stdout,
        force=True,
    )


def main() -> None:
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    _configure_logging()

    # Import arq *after* the policy is in place.
    from arq.worker import create_worker

    from pynote_worker.main import WorkerSettings

    worker = create_worker(WorkerSettings)  # type: ignore[arg-type]
    worker.run()


if __name__ == "__main__":
    main()
