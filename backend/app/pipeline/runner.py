"""Runs jobs as background tasks in this process, resumes orphaned jobs, and fails jobs on request.

Used by the server (app/main.py) and the CLI, so both get the same watchdog and resume behaviour.
"""

import asyncio
import contextlib
import logging
from datetime import timedelta

from app.config import settings
from app.models.job import Job, JobError, now
from app.pipeline import checkpoint
from app.pipeline.orchestrator import Deps, run_job

log = logging.getLogger(__name__)


class JobRunner:
    def __init__(self, deps: Deps):
        self.deps = deps
        self.tasks: dict[str, asyncio.Task] = {}
        self.jobs: dict[str, Job] = {}

    def is_running(self, job_id) -> bool:
        return str(job_id) in self.tasks

    def start(self, job: Job) -> asyncio.Task:
        key = str(job.id)
        if key in self.tasks:
            return self.tasks[key]
        self.jobs[key] = job
        self.tasks[key] = asyncio.create_task(self._run(job), name=f"job-{key}")
        return self.tasks[key]

    async def _run(self, job: Job) -> Job:
        key = str(job.id)
        try:
            return await run_job(job, self.deps)
        except asyncio.CancelledError:
            return job  # stopped by fail() or shutdown(); they record why
        except Exception:  # noqa: BLE001 - run_job already saved and announced the failure
            return job
        finally:
            self.tasks.pop(key, None)
            self.jobs.pop(key, None)

    async def wait(self, job_id) -> Job:
        """Wait for a job this runner is running; returns it in its final state."""
        return await self.tasks[str(job_id)]

    async def cancel(self, job_id) -> None:
        """Stop a running job and wait until it has stopped, recording nothing (e.g. it is being deleted)."""
        task = self.tasks.get(str(job_id))
        if task is not None:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    async def fail(self, job_id, message: str) -> None:
        """Stop a running job and mark it failed (it can be resumed later)."""
        key = str(job_id)
        job, task = self.jobs.get(key), self.tasks.get(key)
        if task is not None:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        if job is None:
            return
        job.status = "failed"
        job.error = JobError(stage=job.stage, message=message)
        await checkpoint.save_fields(job, "status", "error", "usage")
        self.deps.events.publish(job.id, "failed", stage=job.stage, message=message)
        log.error("Job %s failed: %s", job.id, message)

    async def resume_orphans(self) -> list[Job]:
        """Restart `running` jobs whose process stopped ticking (killed or crashed)."""
        cutoff = now() - timedelta(seconds=settings.resume_after_seconds)
        orphans = await Job.find(
            {
                "status": "running",
                "$or": [
                    {"alive_at": {"$lt": cutoff}},
                    {"alive_at": {"$exists": False}},
                ],
            }
        ).to_list()
        for job in orphans:
            if not self.is_running(job.id):
                log.warning(
                    "Resuming job %s (%s), interrupted during %s",
                    job.id,
                    job.topic,
                    job.stage,
                )
                self.start(job)
        return orphans

    async def shutdown(self) -> None:
        """Stop every job without marking it failed: the next startup resumes it."""
        tasks = list(self.tasks.values())
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
