"""FastAPI app. On startup: connect to MongoDB, resume jobs whose process died, start the watchdog.

Run without --reload while jobs are running (a reload restarts the process and interrupts them;
they are resumed on the next startup).
"""

import asyncio
import contextlib
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api import account, auth, billing, health, jobs, videos, voices
from app.config import settings

log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    from app.agents.llm import AgentError
    from app.db import init_db
    from app.pipeline.deps import build_deps
    from app.pipeline.runner import JobRunner
    from app.pipeline.watchdog import run_watchdog

    client = await init_db()
    watchdog = None
    try:
        deps = await build_deps(f"{settings.public_base_url}/media")
    except AgentError as exc:  # e.g. no OPENAI_API_KEY: serve the API, refuse new jobs
        log.error("Pipeline unavailable: %s", exc)
        app.state.setup_error = str(exc)
    else:
        runner = JobRunner(deps)
        app.state.runner = runner
        resumed = await runner.resume_orphans()
        if resumed:
            log.warning("Resumed %d interrupted job(s)", len(resumed))
        # The server owns orphaned jobs: it resumes any whose process died.
        watchdog = asyncio.create_task(run_watchdog(runner, adopt_orphans=True))
    try:
        yield
    finally:
        if watchdog is not None:
            watchdog.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await watchdog
        if app.state.runner is not None:
            await app.state.runner.shutdown()  # left `running`: resumed on next startup
        await client.close()


app = FastAPI(title="Mindsketch.ai", lifespan=lifespan)
app.state.runner = None
app.state.setup_error = None

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    # The renderer page (served on a localhost port) fetch()es icons from /media.
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(auth.router)
app.include_router(account.router)
app.include_router(billing.router)
app.include_router(jobs.router)
app.include_router(videos.router)
app.include_router(voices.router)

settings.media_dir.mkdir(parents=True, exist_ok=True)
app.mount("/media", StaticFiles(directory=settings.media_dir), name="media")
