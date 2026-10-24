"""Jobs: start, list, read, resume, delete, and follow live (Server-Sent Events)."""

import asyncio
import json
import shutil
from collections.abc import AsyncIterator

from beanie import PydanticObjectId
from fastapi import APIRouter, HTTPException, Query, Request, Response, status
from fastapi.sse import EventSourceResponse, format_sse_event

from app.auth import CurrentUser, can_see, check_video_limits, owner_filter
from app.config import settings
from app.models.account import VideoStart
from app.models.job import Job, JobOptions
from app.models.user import User
from app.models.video import Video
from app.pipeline.events import TERMINAL
from app.pricing import job_cost
from app.schemas.api import (
    JobCreate,
    JobCreated,
    JobSnapshot,
    JobSummary,
    SceneSnapshot,
)
from app.tts.voices import voice_label

router = APIRouter(prefix="/api/jobs", tags=["jobs"])

# While a job is quiet, re-send its state this often: it doubles as a keep-alive and covers jobs
# run by another process (e.g. the CLI), whose events never reach this server's event bus.
SNAPSHOT_EVERY_SECONDS = 5.0


def media_url(path: str | None) -> str | None:
    """Relative, so the browser fetches it from wherever it loaded the app (Vite proxy in dev)."""
    return f"/media/{path}" if path else None


def snapshot(job: Job) -> JobSnapshot:
    streaming = any(s.status == "streamed" for s in job.scenes)
    return JobSnapshot(
        id=str(job.id),
        topic=job.topic,
        status=job.status,
        stage=job.stage,
        progress=job.progress,
        attempts=job.attempts,
        title=job.plan.title if job.plan else None,
        options=job.options.model_dump(),
        voice=voice_label(job.options.voice),
        scene_count=len(job.scenes) or (len(job.plan.scenes) if job.plan else 0),
        scenes=[
            SceneSnapshot(
                id=s.id,
                index=s.index,
                status=s.status,
                title=(s.spec or {}).get("title"),
                layout=(s.spec or {}).get("layout"),
                error=s.error,
            )
            for s in job.scenes
        ],
        playlist_url=media_url(job.playlist_path) if streaming else None,
        video_url=media_url(job.final_video_path),
        thumbnail_url=media_url(job.thumbnail_path),
        duration=job.duration,
        cost_usd=job_cost(job.usage)["total_usd"] if job.usage else None,
        error=job.error.model_dump() if job.error else None,
        created_at=job.created_at,
        updated_at=job.updated_at,
    )


def _runner(request: Request):
    return request.app.state.runner


async def _load(job_id: str, request: Request, user: User) -> Job:
    """The job, preferring the live in-memory copy when this process is running it.

    Someone else's job is reported as missing (404), so its existence isn't revealed.
    """
    runner = _runner(request)
    job = runner.jobs.get(job_id) if runner else None
    if job is None:
        try:
            job = await Job.get(PydanticObjectId(job_id))
        except Exception:  # noqa: BLE001 - malformed id
            job = None
    if job is None or not can_see(user, job.owner_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"No job {job_id}")
    return job


def _require_runner(request: Request):
    runner = _runner(request)
    if runner is None:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=request.app.state.setup_error or "pipeline not available",
        )
    return runner


@router.post("", status_code=status.HTTP_202_ACCEPTED, response_model=JobCreated)
async def create_job(
    body: JobCreate, request: Request, user: CurrentUser
) -> JobCreated:
    runner = _require_runner(request)
    await check_video_limits(user)
    job = await Job(
        topic=body.topic,
        owner_id=user.id,
        options=JobOptions(
            background=body.background,
            aspect=body.aspect,
            **({"voice": body.voice} if body.voice else {}),
        ),
    ).insert()
    await VideoStart(owner_id=user.id, job_id=job.id).insert()
    runner.start(job)
    return JobCreated(job_id=str(job.id))


@router.get("", response_model=list[JobSummary])
async def list_jobs(
    user: CurrentUser, limit: int = Query(50, ge=1, le=200)
) -> list[JobSummary]:
    """Newest first, without the heavy fields (plan, script, word timings)."""
    fields = {
        "topic": 1,
        "plan.title": 1,
        "status": 1,
        "stage": 1,
        "progress": 1,
        "thumbnail_path": 1,
        "usage": 1,
        "created_at": 1,
    }
    cursor = (
        Job.get_pymongo_collection()
        .find(owner_filter(user), fields)
        .sort("created_at", -1)
    )
    return [
        JobSummary(
            id=str(doc["_id"]),
            topic=doc["topic"],
            title=(doc.get("plan") or {}).get("title"),
            status=doc.get("status", "queued"),
            stage=doc.get("stage", "queued"),
            progress=doc.get("progress", 0.0),
            thumbnail_url=media_url(doc.get("thumbnail_path")),
            cost_usd=job_cost(doc["usage"])["total_usd"] if doc.get("usage") else None,
            created_at=doc["created_at"],
        )
        for doc in await cursor.to_list(limit)
    ]


@router.get("/{job_id}", response_model=JobSnapshot)
async def get_job(job_id: str, request: Request, user: CurrentUser) -> JobSnapshot:
    return snapshot(await _load(job_id, request, user))


@router.post(
    "/{job_id}/resume", status_code=status.HTTP_202_ACCEPTED, response_model=JobCreated
)
async def resume_job(job_id: str, request: Request, user: CurrentUser) -> JobCreated:
    """Continue a failed (or orphaned) job from its last checkpoint."""
    runner = _require_runner(request)
    job = await _load(job_id, request, user)
    if runner.is_running(job.id):
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Job is already running")
    if job.status == "completed":
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Job is already completed")
    runner.start(job)
    return JobCreated(job_id=str(job.id))


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_job(job_id: str, request: Request, user: CurrentUser) -> Response:
    """Delete a job, its gallery video and all its files. A running job is stopped first.

    The video still counts toward today's quota (it was made, and paid for).
    """
    job = await _load(job_id, request, user)
    runner = _runner(request)
    if runner is not None:
        await runner.cancel(job.id)
    await Video.find(Video.job_id == job.id).delete()
    await Job.find(Job.id == job.id).delete()
    media_root = runner.deps.media_root if runner else settings.media_dir
    folder = media_root / "jobs" / str(job.id)
    await asyncio.to_thread(shutil.rmtree, folder, ignore_errors=True)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _sse(event: str, data) -> bytes:
    return format_sse_event(event=event, data_str=json.dumps(data, default=str))


# Returns the streaming response itself (not a `yield`-based path operation), so an unknown job
# can still get a plain 404 before the stream starts.
@router.get("/{job_id}/events")
async def job_events(
    job_id: str, request: Request, user: CurrentUser
) -> EventSourceResponse:
    """Live progress: a `snapshot` first, then pipeline events, until the job finishes.

    Reconnecting is safe: every connection starts with the full current state.
    """
    runner = _runner(request)
    # Subscribe before reading the state, so no event can slip in between.
    sub = runner.deps.events.open(job_id) if runner else None
    try:
        job = await _load(job_id, request, user)
    except HTTPException:
        if sub:
            sub.close()
        raise

    async def stream() -> AsyncIterator[bytes]:
        try:
            yield _sse("snapshot", snapshot(job).model_dump(mode="json"))
            # Stop on a terminal event, or when a re-read shows the job finished elsewhere.
            # (Not on the in-memory status alone: it flips just before `completed` is published.)
            done = job.status in TERMINAL
            while not done:
                event = await sub.get(SNAPSHOT_EVERY_SECONDS) if sub else None
                if event is not None:
                    yield _sse(event.type, {**event.data, "at": event.at})
                    if event.type not in TERMINAL:
                        continue
                try:
                    current = await _load(job_id, request, user)
                except HTTPException:
                    return  # deleted meanwhile: end the stream (a reconnect then gets a 404)
                yield _sse("snapshot", snapshot(current).model_dump(mode="json"))
                done = event is not None or current.status in TERMINAL
        finally:
            if sub:
                sub.close()

    return EventSourceResponse(
        stream(), headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    )
