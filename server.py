"""Mindsketch Tutor: a no-login server that runs the Mindsketch video pipeline with Sarvam voices.

Run (inside this folder):  backend/.venv/bin/python server.py   ->  http://localhost:8100
Needs MongoDB and the render service (cd renderer && npm run server). All settings: ./.env
The pipeline code in backend/app is used as it is; this file swaps in a Sarvam-aware TTS provider.
"""

import asyncio
import contextlib
import logging
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

HERE = Path(__file__).resolve().parent
BACKEND = HERE / "backend"
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(BACKEND))
os.chdir(BACKEND)  # MEDIA_DIR=./media resolves to backend/media

from beanie import PydanticObjectId  # noqa: E402
from dotenv import load_dotenv  # noqa: E402

# Before importing app.config: these env vars become the backend's settings.
load_dotenv(HERE / ".env")
PORT = int(os.environ.get("TUTOR_PORT", "8100"))

from fastapi import FastAPI, HTTPException  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

import sarvam  # noqa: E402
import tutor  # noqa: E402
from app import auth  # noqa: E402
from app.api import jobs  # noqa: E402
from app.config import settings  # noqa: E402
from app.models.job import Job, JobOptions  # noqa: E402
from app.models.user import User  # noqa: E402
from sarvam_tts import RoutedTTS, make_voice, parse_voice  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("tutor.server")

GUEST_EMAIL = "guest@mindsketch.local"
_guest: User | None = None


async def guest_user() -> User:
    global _guest
    if _guest is None:
        _guest = await User.find_one(User.email == GUEST_EMAIL)
        if _guest is None:
            _guest = await User(
                email=GUEST_EMAIL, name="Guest learner", password_hash="!", plan="max"
            ).insert()
    return _guest


ICONS_ARCHIVE = HERE / "data" / "icons.tar.gz"


async def import_icons() -> None:
    """First run on a fresh database / media folder: load the bundled icon library."""
    from app.models.icon import Icon
    from app.transfer import import_data

    media_root = settings.media_dir.resolve()
    if await Icon.count() and any((media_root / "icons").glob("*.svg")):
        return
    if ICONS_ARCHIVE.exists():
        icons, files = await import_data(ICONS_ARCHIVE, media_root)
        log.info("Imported the icon library: %d icons, %d files", icons, files)


def job_language(job: Job) -> str:
    voice = job.options.voice
    return parse_voice(voice)[0] if voice.startswith("sarvam:") else "en-IN"


# Slot fields the renderer draws as words (schemas/scene.py). Numbers, icon queries and
# appear_on cue phrases stay as they are.
SCREEN_TEXT = {"title", "heading", "subheading", "label", "arrow_labels", "header", "caption", "text", "date_label"}
_translate_slots = asyncio.Semaphore(4)


def _map_text(node, fn, key: str | None = None):
    if isinstance(node, dict):
        return {k: _map_text(v, fn, k) for k, v in node.items()}
    if isinstance(node, list):
        return [_map_text(v, fn, key) for v in node]
    if isinstance(node, str) and key in SCREEN_TEXT and node.strip():
        return fn(node)
    return node


async def translate_or_keep(text: str, lang: str) -> str:
    async with _translate_slots:
        try:
            return await sarvam.translate(text, lang) or text
        except Exception:  # noqa: BLE001 - an English label beats a failed video
            log.warning("Could not translate %r into %s", text, lang, exc_info=True)
            return text


async def localize_scene(scene: dict, lang: str) -> dict:
    """The scene's on-screen words in `lang` (the pipeline designs every scene in English)."""
    texts: set[str] = set()
    _map_text(scene, lambda s: texts.add(s) or s)
    found = list(texts)
    done = dict(zip(found, await asyncio.gather(*(translate_or_keep(t, lang) for t in found))))
    return _map_text(scene, lambda s: done.get(s, s))


def localized_render(render):
    """Wraps deps.render: translate the scene's words into the job's language just before drawing."""

    async def run(props: dict, video: Path) -> dict:
        # <media>/jobs/<job id>/scenes/sNN.mp4
        job = await Job.get(PydanticObjectId(video.parent.parent.name))
        lang = job_language(job) if job else "en-IN"
        if lang != "en-IN":
            props = {**props, "scene": await localize_scene(props["scene"], lang)}
        return await render(props, video)

    return run


@asynccontextmanager
async def lifespan(app: FastAPI):
    from app.db import init_db
    from app.pipeline.deps import build_deps
    from app.pipeline.runner import JobRunner
    from app.pipeline.watchdog import run_watchdog

    client = await init_db()
    await import_icons()
    await guest_user()
    deps = await build_deps(f"http://localhost:{PORT}/media")
    deps.tts = RoutedTTS(edge=deps.tts)
    deps.render = localized_render(deps.render)
    runner = JobRunner(deps)
    app.state.runner = runner
    await runner.resume_orphans()
    watchdog = asyncio.create_task(run_watchdog(runner, adopt_orphans=True))
    if not os.environ.get("SARVAM_API_KEY"):
        log.error("SARVAM_API_KEY is missing: put it in sarvam_ai/.env")
    log.info("Mindsketch Tutor on http://localhost:%d", PORT)
    try:
        yield
    finally:
        watchdog.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await watchdog
        await runner.shutdown()
        await client.close()


app = FastAPI(title="Mindsketch Tutor", lifespan=lifespan)
app.state.runner = None
app.state.setup_error = None
# Everyone is the guest here: the reused jobs router (GET job, SSE events) works without a cookie.
app.dependency_overrides[auth.current_user] = guest_user
# The renderer page (another localhost port) fetch()es icon SVGs from /media, which needs CORS.
app.add_middleware(CORSMiddleware, allow_origin_regex=r"http://(localhost|127\.0\.0\.1):\d+")
app.include_router(jobs.router)
app.include_router(tutor.router)


class StartIn(BaseModel):
    topic: str = Field(min_length=2, max_length=300)
    language: str = "en-IN"
    english_topic: str | None = None  # already translated (from /transcribe)
    speaker: str | None = None


@app.post("/api/learn/start", status_code=202)
async def start(body: StartIn) -> dict:
    runner = app.state.runner
    if runner is None:
        raise HTTPException(503, detail="pipeline not ready")
    sarvam.lang_info(body.language)
    english = (body.english_topic or "").strip()
    if not english:
        english = body.topic.strip()
        try:
            typed = await sarvam.detect(english)
            if typed != "en-IN":
                english = await sarvam.translate(english, "en-IN", source=typed)
        except Exception:  # noqa: BLE001 - detection is a nicety; use the text as typed
            log.warning("Could not detect/translate topic %r", english, exc_info=True)
    guest = await guest_user()
    job = await Job(
        topic=english[:300],
        owner_id=guest.id,
        options=JobOptions(voice=make_voice(body.language, body.speaker)),
    ).insert()
    runner.start(job)
    return {"job_id": str(job.id), "english_topic": english}


@app.get("/api/learn/recent")
async def recent() -> list[dict]:
    """Finished tutor videos (Sarvam voices), newest first: handy as a demo backup."""
    found = (
        await Job.find({"options.voice": {"$regex": "^sarvam:"}, "status": "completed"})
        .sort("-created_at")
        .limit(12)
        .to_list()
    )
    titles = await asyncio.gather(*(localized_title(j) for j in found))
    return [
        {
            "job_id": str(j.id),
            "topic": j.topic,
            "title": title,
            "language": job_language(j),
        }
        for j, title in zip(found, titles)
    ]


_titles: dict[str, str] = {}  # job id -> title in the lesson's language


async def localized_title(job: Job) -> str:
    title = job.plan.title if job.plan else job.topic
    lang = job_language(job)
    if lang == "en-IN":
        return title
    key = str(job.id)
    if key not in _titles:
        translated = await translate_or_keep(title, lang)
        if translated == title:
            return title  # failed: try again next time
        _titles[key] = translated
    return _titles[key]


settings.media_dir.mkdir(parents=True, exist_ok=True)
app.mount("/media", StaticFiles(directory=settings.media_dir), name="media")
app.mount("/", StaticFiles(directory=HERE / "web", html=True), name="web")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="info")
