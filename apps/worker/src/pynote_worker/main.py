"""arq WorkerSettings entry point.

Run:
    uv run arq pynote_worker.main.WorkerSettings
"""

from typing import Any, ClassVar

from arq.connections import RedisSettings

from pynote_core.settings import get_settings
from pynote_core.tracing import configure_tracing
from pynote_worker.tasks import (
    embed_source,
    generate_mind_map_task,
    noop_task,
    outline_source,
    parse_source,
    ping_llm_task,
)


async def startup(ctx: dict[str, Any]) -> None:
    configure_tracing()
    ctx["started"] = True


async def shutdown(ctx: dict[str, Any]) -> None:
    pass


_settings = get_settings()


class WorkerSettings:
    """arq looks up these class attrs by name; they're config, not mutable state."""

    redis_settings: ClassVar = RedisSettings.from_dsn(_settings.redis_url)
    functions: ClassVar = [
        noop_task,
        ping_llm_task,
        parse_source,
        embed_source,
        outline_source,
        generate_mind_map_task,
    ]
    on_startup: ClassVar = startup
    on_shutdown: ClassVar = shutdown
    max_jobs: ClassVar[int] = _settings.worker_concurrency
    job_timeout: ClassVar[int] = 60 * 30  # generous for big-PDF parsing in later milestones
    keep_result: ClassVar[int] = 60 * 60 * 24
    # arq's default poll_delay=0.5s is ~2 Redis cmds/sec ≈ 5M/month — it would
    # exhaust Upstash's 500k free monthly quota in ~3 days (DEPLOY.md §2.2/§4).
    # 5s adds at most 5s of ingest latency (invisible next to cold starts) and
    # keeps steady-state polling well under quota.
    poll_delay: ClassVar[float] = 5.0
    health_check_interval: ClassVar[int] = 300
