"""Targeted checkpoint writes for a running job.

Beanie's `job.save()` writes the whole document and rebuilds nested models, so parallel scenes
saving the job would overwrite each other's progress. During a run every writer instead `$set`s
only the paths it owns: one scene (`scenes.<i>`) or named top-level fields, from the in-memory job.

Writes for one job go through a lock, so the snapshot taken first always lands first (two
in-flight updates can't arrive out of order and leave an older state in the database).
"""

import asyncio
from collections import defaultdict

from beanie.odm.utils.encoder import Encoder

from app.models.job import Job, now

_encoder = Encoder()
_locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)


async def _set(job: Job, build: callable) -> None:
    async with _locks[str(job.id)]:
        values = _encoder.encode(build())  # snapshot taken inside the lock
        await Job.get_pymongo_collection().update_one({"_id": job.id}, {"$set": values})


def forget(job: Job) -> None:
    """Drop the job's lock once it stops running."""
    _locks.pop(str(job.id), None)


async def save_fields(job: Job, *names: str) -> None:
    """Persist these top-level fields (plus updated_at) from the in-memory job."""

    def build() -> dict:
        job.updated_at = now()
        return {name: getattr(job, name) for name in (*names, "updated_at")}

    await _set(job, build)


async def save_scene(job: Job, index: int) -> None:
    """Persist one scene, and record progress (which also feeds the watchdog)."""

    def build() -> dict:
        job.heartbeat_at = job.updated_at = now()
        return {
            f"scenes.{index}": job.scenes[index],
            "progress": job.progress,
            "heartbeat_at": job.heartbeat_at,
            "updated_at": job.updated_at,
            "usage": job.usage,
        }

    await _set(job, build)


async def touch_alive(job: Job) -> None:
    """The process running this job is still alive."""

    def build() -> dict:
        job.alive_at = now()
        return {"alive_at": job.alive_at}

    await _set(job, build)
