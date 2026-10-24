"""Keeps jobs from hanging silently.

Every `watchdog_interval_seconds`:
- a job this process runs with no progress (heartbeat_at) for `watchdog_stall_seconds` is cancelled
  and marked failed "stalled" (finished work is kept, so it can be resumed);
- in the server (`adopt_orphans=True`), a `running` job whose process stopped ticking (alive_at
  older than `resume_after_seconds`) is resumed here. This covers a server restarted so quickly
  that the dead process's last tick still looked fresh at startup.
"""

import asyncio
import logging
from datetime import datetime, timedelta

from app.config import settings
from app.models.job import Job, now
from app.pipeline.runner import JobRunner

log = logging.getLogger(__name__)


def stalled(jobs: dict[str, Job], at: datetime, stall_seconds: float) -> list[str]:
    """Ids of jobs whose last progress is older than the stall window."""
    limit = timedelta(seconds=stall_seconds)
    return [key for key, job in jobs.items() if at - job.heartbeat_at > limit]


async def check_once(
    runner: JobRunner,
    stall_seconds: float | None = None,
    adopt_orphans: bool = False,
) -> list[str]:
    """One watchdog pass. Returns the ids of jobs it marked failed."""
    stall_seconds = stall_seconds or settings.watchdog_stall_seconds
    at = now()
    failed = []
    for key in stalled(dict(runner.jobs), at, stall_seconds):
        job = runner.jobs.get(key)
        if job is None:
            continue
        idle = (at - job.heartbeat_at).total_seconds()
        await runner.fail(
            key, f"stalled: no progress for {idle:.0f}s during {job.stage}"
        )
        failed.append(key)
    if adopt_orphans:
        await runner.resume_orphans()
    return failed


async def run_watchdog(
    runner: JobRunner, interval: float | None = None, adopt_orphans: bool = False
) -> None:
    interval = interval or settings.watchdog_interval_seconds
    while True:
        await asyncio.sleep(interval)
        try:
            await check_once(runner, adopt_orphans=adopt_orphans)
        except Exception:
            log.exception("Watchdog pass failed")
