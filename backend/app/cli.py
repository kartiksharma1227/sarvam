"""Command-line entry point.

    python -m app.cli "Explain how credit scores work"   generate a video from a topic (Phase 3)
    python -m app.cli "..." --background graph_paper     same, on graph paper
    python -m app.cli "..." --aspect 9:16 --voice en-US-AvaNeural   vertical video, another narrator
    python -m app.cli --resume <job_id>                  continue a failed or interrupted job
    python -m app.cli --sample [name]                    narrate + render a hand-written sample (Phase 2)

Needs the render service running: cd renderer && npm run server
Topic mode also needs OPENAI_API_KEY, LLM_MODEL_MAIN and MONGODB_URI in backend/.env,
and a seeded icon library: python -m app.icons.seed
"""

import argparse
import asyncio
import json
import logging
import time
from pathlib import Path

from app.config import settings
from app.ffmpeg import concat_videos
from app.media_server import serve_media
from app.pipeline.scene_props import build_render_props
from app.pipeline.timing import CueResult
from app.pricing import job_cost
from app.render.client import RenderServiceError, check_health, render_scene
from app.tts.base import get_provider, synthesize_cached

SAMPLES_DIR = Path(__file__).resolve().parents[2] / "renderer" / "src" / "samples"
RENDER_PARALLEL = 2


def _print_report(
    index: int, scene: dict, duration: float, cues: list[CueResult]
) -> None:
    print(
        f'\ns{index:02d} {scene["layout"]:<11} audio {duration:5.2f}s  "{scene["title"]}"'
    )
    for cue in cues:
        matched = f"-> {cue.matched!r}" if cue.matched and cue.method == "fuzzy" else ""
        print(
            f"    {cue.start:5.2f}s  {cue.target:<14} {cue.phrase!r:<22} {cue.method} {matched}"
        )


async def run_sample(name: str) -> Path:
    sample_path = SAMPLES_DIR / f"{name}.json"
    if not sample_path.exists():
        available = ", ".join(p.stem for p in sorted(SAMPLES_DIR.glob("*.json")))
        raise SystemExit(f"No sample {name!r}. Available: {available}")
    samples = json.loads(sample_path.read_text())

    media_root = settings.media_dir.resolve()
    out_dir = media_root / "samples" / name
    await check_health()

    provider = get_provider()
    print(f"Narrating {len(samples)} scenes with {provider.name} ({provider.voice})...")
    tts_results = await asyncio.gather(
        *(
            synthesize_cached(
                provider, s["scene"]["narration"], out_dir / "audio" / f"s{i:02d}.mp3"
            )
            for i, s in enumerate(samples, 1)
        )
    )

    with serve_media(media_root) as base_url:
        props_list = []
        for i, (sample, tts) in enumerate(zip(samples, tts_results, strict=True), 1):
            audio_url = f"{base_url}/{tts.audio_path.resolve().relative_to(media_root).as_posix()}"
            props, cues = build_render_props(sample, tts, audio_url)
            _print_report(i, sample["scene"], tts.duration, cues)
            props_path = out_dir / "scenes" / f"s{i:02d}.props.json"
            props_path.parent.mkdir(parents=True, exist_ok=True)
            props_path.write_text(json.dumps(props, indent=2))
            props_list.append(props)

        print(f"\nRendering {len(props_list)} scenes ({RENDER_PARALLEL} at a time)...")
        limit = asyncio.Semaphore(RENDER_PARALLEL)

        async def render(i: int, props: dict) -> Path:
            async with limit:
                out = out_dir / "scenes" / f"s{i:02d}.mp4"
                await render_scene(props, out)
                print(f"  rendered s{i:02d}")
                return out

        scene_paths = await asyncio.gather(
            *(render(i, p) for i, p in enumerate(props_list, 1))
        )

    final = concat_videos(list(scene_paths), out_dir / f"{name}.mp4")
    print(f"\nDone -> {final}")
    return final


def _event_printer(started: float):
    """Print pipeline events the way the CLI always has, plus per-scene progress."""

    def show(event) -> None:
        data = event.data
        if event.type == "stage":
            print(f"  [{data['stage']}] {data['label']}")
        elif event.type == "scene":
            print(f"    {data['scene_id']:<4} {data['status']}")
        elif event.type == "stream_ready":
            print(
                f"  >> Stream playable after {time.monotonic() - started:.0f}s: "
                f"{settings.media_dir.resolve() / data['playlist_path']}"
            )
        elif event.type == "failed":
            print(f"  [failed] {data['stage']}: {data['message']}")

    return show


async def run_topic(
    topic: str | None, options: dict, resume: str | None, owner: str | None = None
) -> None:
    from beanie import PydanticObjectId

    from app.db import init_db
    from app.models.job import Job, JobOptions
    from app.pipeline.deps import build_deps
    from app.pipeline.runner import JobRunner
    from app.pipeline.watchdog import run_watchdog

    await check_health()
    client = await init_db()
    try:
        if resume:
            job = await Job.get(PydanticObjectId(resume))
            if job is None:
                raise SystemExit(f"No job with id {resume}")
            print(f"Resuming job {job.id} ({job.status} at {job.stage}): {job.topic}")
        else:
            owner_id = None
            if owner:
                from app.models.user import User

                account = await User.find_one(User.email == owner.strip().lower())
                if account is None:
                    raise SystemExit(f"No account with email {owner}")
                owner_id = account.id
            job = await Job(
                topic=topic, options=JobOptions(**options), owner_id=owner_id
            ).insert()
            print(f"Job {job.id}: {topic}")

        media_root = settings.media_dir.resolve()
        started = time.monotonic()
        with serve_media(media_root) as base_url:
            deps = await build_deps(base_url)
            library_size = len(await deps.icons.names())
            if library_size < 20:
                print(
                    f"  ! The icon library has only {library_size} icons; most will be drawn new "
                    "(max 3 per video). Build it first: python -m app.icons.seed"
                )
            deps.events.listen(_event_printer(started))
            runner = JobRunner(deps)
            watchdog = asyncio.create_task(run_watchdog(runner))
            try:
                runner.start(job)
                job = await runner.wait(job.id)
            finally:
                watchdog.cancel()
        elapsed = time.monotonic() - started

        if job.status != "completed":
            error = job.error
            raise SystemExit(
                f"Job failed during {error.stage}: {error.message}\n"
                f"Finished scenes are saved. Continue with: python -m app.cli --resume {job.id}"
            )

        print(f"\n{job.plan.title}  ({len(job.plan.scenes)} scenes)")
        for planned, scene in zip(job.plan.scenes, job.scenes, strict=True):
            print(
                f"  {planned.id} {planned.purpose:<9} {planned.layout:<11} {scene.spec['title']}"
            )
        for scene in job.scenes:
            cues = [CueResult(**c) for c in scene.cues]
            _print_report(scene.index + 1, scene.spec, scene.duration, cues)

        print("\nIcons:")
        for query, choice in job.icon_choices.items():
            print(f"  {query!r:<28} -> {choice.name:<22} {choice.how}")
        if job.icons_generated:
            print(f"  newly drawn: {', '.join(job.icons_generated)}")

        print("\nTokens:")
        for model, use in job.usage.get("by_model", {}).items():
            print(
                f"  {model}: {use['calls']} calls, {use['input_tokens']} in / {use['output_tokens']} out"
            )
        print(f"  validation retries: {job.usage.get('validation_retries', 0)}")
        cost = job_cost(job.usage)
        unpriced = (
            f" (no price for: {', '.join(cost['unpriced'])})"
            if cost["unpriced"]
            else ""
        )
        print(f"  estimated cost: ${cost['total_usd']:.2f}{unpriced}")
        print(
            f"\nDone in {elapsed:.0f}s: {job.duration:.1f}s of video -> {media_root / job.final_video_path}"
        )
        print(f"Live stream (HLS): {media_root / job.playlist_path}")
        print(f"Job id: {job.id}")
    finally:
        await client.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="python -m app.cli", description="Mindsketch.ai command line"
    )
    parser.add_argument(
        "topic", nargs="?", help='what to explain, e.g. "How do vaccines work?"'
    )
    parser.add_argument(
        "--background", choices=["plain", "graph_paper"], default="plain"
    )
    parser.add_argument(
        "--aspect",
        choices=["16:9", "9:16"],
        default="16:9",
        help="9:16 = vertical video",
    )
    parser.add_argument(
        "--voice", help="narrator voice id, e.g. en-US-AvaNeural (see GET /api/voices)"
    )
    parser.add_argument(
        "--owner",
        metavar="EMAIL",
        help="put the video in this account (default: no owner, seen by the admin)",
    )
    parser.add_argument(
        "--resume", metavar="JOB_ID", help="continue a failed or interrupted job"
    )
    parser.add_argument(
        "--sample",
        nargs="?",
        const="credit-scores",
        help="narrate and render a sample file",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.WARNING, format="  ! %(message)s")
    try:
        if args.sample:
            asyncio.run(run_sample(args.sample))
        elif args.topic or args.resume:
            options = {"background": args.background, "aspect": args.aspect}
            if args.voice:
                from app.tts.voices import VOICE_IDS

                if args.voice not in VOICE_IDS:
                    raise SystemExit(
                        f"Unknown voice {args.voice}. Choose from: {', '.join(sorted(VOICE_IDS))}"
                    )
                options["voice"] = args.voice
            asyncio.run(run_topic(args.topic, options, args.resume, args.owner))
        else:
            parser.print_help()
    except RenderServiceError as exc:
        raise SystemExit(str(exc)) from exc
    except Exception as exc:
        # Setup problems (missing key, database unreachable) and agent failures: one clear line.
        from app.agents.llm import AgentError
        from app.db import DatabaseError

        if isinstance(exc, AgentError | DatabaseError):
            raise SystemExit(f"Error: {exc}") from exc
        raise


if __name__ == "__main__":
    main()
