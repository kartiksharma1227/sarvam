"""Runs a job end to end: plan -> script -> edit -> all scenes in parallel -> final video.

Each scene is its own task: design and narration run concurrently, then icons, render, and
segmenting into the live HLS stream. Scenes queue for the shared LLM, TTS and render slots with
scene 1 first, so the stream can start as early as possible.

Every step saves a checkpoint (targeted `$set`s, see checkpoint.py) and skips work that is already
done, so re-running a failed or interrupted job resumes where it stopped.
"""

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path

from app.agents.designer import design_scene
from app.agents.editor import edit_script
from app.agents.llm import LLM, Usage
from app.agents.planner import plan_lesson
from app.agents.scriptwriter import write_script
from app.config import settings
from app.ffmpeg import concat_videos, extract_thumbnail, probe_duration
from app.icons.library import IconLibrary
from app.models.job import SCENE_STEPS, Job, JobError, SceneState, now
from app.models.video import Video
from app.pipeline import checkpoint
from app.pipeline.events import EventBus
from app.pipeline.limits import PrioritySemaphore
from app.pipeline.scene_props import build_render_props
from app.render.client import render_scene
from app.render.hls import StreamWriter, segment_scene
from app.tts.base import TTSProvider, synthesize_cached

log = logging.getLogger(__name__)

# Frame size per aspect ratio; the renderer lays every scene out for the canvas it is given.
RENDER_SIZES = {"16:9": (1920, 1080), "9:16": (1080, 1920)}
FPS = 30


def render_options(aspect: str) -> dict:
    width, height = RENDER_SIZES[aspect]
    return {"fps": FPS, "width": width, "height": height}


STAGE_LABELS = {
    "planning": "Planning the lesson",
    "scripting": "Writing the script",
    "editing": "Editing the script",
    "scenes": "Designing, narrating and rendering scenes",
    "finalizing": "Joining the final video",
    "done": "Completed",
}

Render = Callable[[dict, Path], Awaitable[dict]]


@dataclass
class Deps:
    llm: LLM
    tts: TTSProvider
    media_root: Path  # absolute MEDIA_DIR
    media_base_url: str  # where the renderer (and players) fetch MEDIA_DIR over HTTP
    icons: IconLibrary
    events: EventBus = field(default_factory=EventBus)
    render: Render = render_scene
    render_concurrency: int = settings.render_concurrency
    llm_concurrency: int = settings.llm_concurrency
    tts_concurrency: int = settings.tts_concurrency

    def __post_init__(self):
        # Shared by every job this process runs, so several jobs never overload the services.
        self.llm_slots = PrioritySemaphore(self.llm_concurrency)
        self.tts_slots = PrioritySemaphore(self.tts_concurrency)
        self.render_slots = PrioritySemaphore(self.render_concurrency)


class SceneError(RuntimeError):
    def __init__(self, step: str, scene_id: str, cause: BaseException):
        self.step, self.scene_id = step, scene_id
        super().__init__(f"{scene_id}: {cause}")


def _progress(job: Job) -> float:
    """Planning and scripting take 0 -> 0.2, scenes 0.2 -> 0.95 (5 steps each), finishing the rest."""
    steps = len(SCENE_STEPS) - 1
    done = sum(s.step() for s in job.scenes)
    return round(0.2 + 0.75 * done / (len(job.scenes) * steps), 3)


async def _keep_alive(job: Job) -> None:
    while True:
        try:
            await checkpoint.touch_alive(job)
        except Exception:
            log.warning("Could not record that job %s is alive", job.id, exc_info=True)
        await asyncio.sleep(settings.alive_interval_seconds)


async def run_job(job: Job, deps: Deps) -> Job:
    publish = lambda type, **data: deps.events.publish(job.id, type, **data)
    job_dir = deps.media_root / "jobs" / str(job.id)

    def rel(path: Path) -> str:
        return path.relative_to(deps.media_root).as_posix()

    def sync_usage() -> None:
        job.usage = deps.llm.usage.as_dict()

    async def set_stage(stage: str, progress: float, detail: str = "") -> None:
        job.stage, job.progress = stage, progress
        job.heartbeat_at = now()
        sync_usage()
        await checkpoint.save_fields(job, "stage", "progress", "heartbeat_at", "usage")
        label = f"{STAGE_LABELS.get(stage, stage)} {detail}".strip()
        publish("stage", stage=stage, label=label, progress=progress)

    async def advance(i: int, status: str, **extra) -> None:
        """Move scene i forward to `status` (never backwards), save it and announce it."""
        scene = job.scenes[i]
        if SCENE_STEPS.index(status) > scene.step():
            scene.status = status
        job.progress = _progress(job)
        sync_usage()
        await checkpoint.save_scene(job, i)
        publish("scene", scene_id=scene.id, index=i, status=status, **extra)

    job.status = "running"
    job.error = None
    job.attempts += 1
    job.models = getattr(deps.llm, "models", {})
    job.alive_at = job.heartbeat_at = now()
    # Keep counting from earlier attempts, so a resumed job reports its total usage.
    deps.llm.usage = Usage.from_dict(job.usage)
    await checkpoint.save_fields(
        job, "status", "error", "attempts", "models", "alive_at", "heartbeat_at"
    )
    alive = asyncio.create_task(_keep_alive(job))

    try:
        if job.plan is None:
            await set_stage("planning", 0.02)
            job.plan = await plan_lesson(deps.llm, job.topic)
            await checkpoint.save_fields(job, "plan")
            await set_stage("planning", 0.08, f"done: {len(job.plan.scenes)} scenes")

        if job.draft_script is None:
            await set_stage("scripting", 0.10)
            job.draft_script = await write_script(deps.llm, job.plan)
            await checkpoint.save_fields(job, "draft_script")
        if job.script is None:
            await set_stage("editing", 0.15)
            job.script = await edit_script(deps.llm, job.plan, job.draft_script)
            await checkpoint.save_fields(job, "script")

        if not job.scenes:
            job.scenes = [
                SceneState(id=s.id, index=i) for i, s in enumerate(job.plan.scenes)
            ]
            await checkpoint.save_fields(job, "scenes")

        stream = StreamWriter(
            job,
            deps.media_root,
            on_stream_ready=lambda path: publish(
                "stream_ready",
                playlist_path=path,
                playlist_url=f"{deps.media_base_url}/{path}",
            ),
        )
        job.playlist_path = stream.playlist_path
        await checkpoint.save_fields(job, "playlist_path")
        await set_stage("scenes", _progress(job), f"({len(job.scenes)} in parallel)")
        # On resume, republish the scenes that were already cut into segments.
        for k in await stream.update():
            await advance(k, "streamed")

        icon_names = await deps.icons.names()
        results = await asyncio.gather(
            *(
                _run_scene(i, job, deps, stream, icon_names, advance, rel)
                for i in range(len(job.scenes))
            ),
            return_exceptions=True,
        )
        failures = [r for r in results if isinstance(r, BaseException)]
        if failures:
            raise failures[0]

        await set_stage("finalizing", 0.96)
        final = await asyncio.to_thread(
            concat_videos,
            [deps.media_root / s.render_path for s in job.scenes],
            job_dir / "final.mp4",
        )
        thumb = await asyncio.to_thread(extract_thumbnail, final, job_dir / "thumb.jpg")
        job.final_video_path, job.thumbnail_path = rel(final), rel(thumb)
        job.duration = round(await asyncio.to_thread(probe_duration, final), 2)
        await stream.update(ended=True)

        if await Video.find_one(Video.job_id == job.id) is None:
            await Video(
                job_id=job.id,
                owner_id=job.owner_id,
                aspect=job.options.aspect,
                title=job.plan.title,
                topic=job.topic,
                duration=job.duration,
                final_video_path=job.final_video_path,
                thumbnail_path=job.thumbnail_path,
            ).insert()

        job.status = "completed"
        await checkpoint.save_fields(
            job, "status", "final_video_path", "thumbnail_path", "duration"
        )
        await set_stage("done", 1.0)
        publish(
            "completed",
            video_url=f"{deps.media_base_url}/{job.final_video_path}",
            thumbnail_url=f"{deps.media_base_url}/{job.thumbnail_path}",
            duration=job.duration,
        )
        return job

    except asyncio.CancelledError:
        # Stopped from outside (watchdog or shutdown); whoever cancelled records why.
        sync_usage()
        raise
    except Exception as exc:
        stage = exc.step if isinstance(exc, SceneError) else job.stage
        log.exception("Job %s failed during %s", job.id, stage)
        job.status = "failed"
        job.error = JobError(stage=stage, message=str(exc)[:1000])
        sync_usage()
        await checkpoint.save_fields(job, "status", "error", "usage")
        publish("failed", stage=stage, message=job.error.message)
        raise
    finally:
        alive.cancel()
        checkpoint.forget(job)


async def _run_scene(
    i: int,
    job: Job,
    deps: Deps,
    stream: StreamWriter,
    icon_names: list[str],
    advance,
    rel,
) -> None:
    """All steps of one scene. Always reach the scene through job.scenes[i]."""
    planned = job.plan.scenes[i]
    narration = job.script.scenes[i].narration
    name = f"s{i + 1:02d}"
    job_dir = deps.media_root / "jobs" / str(job.id)
    step = "designing"

    async def design() -> None:
        if job.scenes[i].spec is None:
            async with deps.llm_slots.slot(i):
                spec = await design_scene(
                    deps.llm, job.plan, planned, narration, icon_names
                )
            job.scenes[i].spec = spec
            await advance(i, "designed")

    async def narrate():
        audio = job_dir / "audio" / f"{name}.mp3"
        async with deps.tts_slots.slot(i):
            tts = await synthesize_cached(
                deps.tts, narration, audio, voice=job.options.voice
            )
        job.scenes[i].audio_path = rel(audio)
        job.scenes[i].duration = tts.duration
        job.scenes[i].words = tts.words
        return tts

    try:
        job.scenes[i].error = None
        designed, tts = await asyncio.gather(
            design(), narrate(), return_exceptions=True
        )
        if isinstance(designed, BaseException):
            raise designed
        step = "narrating"
        if isinstance(tts, BaseException):
            raise tts
        await advance(i, "narrated")

        step = "icons"
        if job.scenes[i].step() < SCENE_STEPS.index("icons"):
            spec = job.scenes[i].spec
            job.scenes[i].icon_map = await deps.icons.icons_for_scene(
                spec["slots"], spec["title"], narration, job
            )
            await checkpoint.save_fields(job, "icon_choices", "icons_generated")
            await advance(i, "icons")

        step = "rendering"
        audio_url = f"{deps.media_base_url}/{job.scenes[i].audio_path}"
        base = {
            "scene": job.scenes[i].spec,
            "icons": {
                query: f"{deps.media_base_url}/{path}"
                for query, path in job.scenes[i].icon_map.items()
            },
            "options": {
                "background": job.options.background,
                "aspect": job.options.aspect,
                **render_options(job.options.aspect),
            },
        }
        props, cues = build_render_props(base, tts, audio_url)
        job.scenes[i].cues = [asdict(c) for c in cues]

        rendered = job.scenes[i].render_path
        if rendered is None or not (deps.media_root / rendered).exists():
            video = job_dir / "scenes" / f"{name}.mp4"
            video.parent.mkdir(parents=True, exist_ok=True)
            (job_dir / "scenes" / f"{name}.props.json").write_text(
                json.dumps(props, indent=2)
            )

            # The earliest unrendered scene always gets a render slot: the stream starts there.
            def is_front() -> bool:
                return all(job.scenes[k].render_path for k in range(i))

            async with deps.render_slots.slot(i, is_front):
                await deps.render(props, video)
                # Recorded before the slot is released, so the next scene counts as the front.
                job.scenes[i].render_path = rel(video)
                job.scenes[i].segments = []  # a new render needs new segments
        await advance(i, "rendered")

        step = "streaming"
        hls_dir = job_dir / "hls"
        segments = job.scenes[i].segments
        if not segments or not all((hls_dir / s.uri).exists() for s in segments):
            job.scenes[i].segments = await asyncio.to_thread(
                segment_scene,
                deps.media_root / job.scenes[i].render_path,
                hls_dir,
                name,
            )
        for k in await stream.update():
            await advance(k, "streamed")

    except asyncio.CancelledError:
        raise
    except Exception as exc:
        job.scenes[i].error = f"{step}: {exc}"[:500]
        await checkpoint.save_scene(job, i)
        raise SceneError(step, job.scenes[i].id, exc) from exc
