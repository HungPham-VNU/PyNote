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
