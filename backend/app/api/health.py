"""Health: is everything a job needs reachable? Never errors; reports `degraded` instead."""

import asyncio

from fastapi import APIRouter, Request

from app.config import settings
from app.schemas.api import Health

router = APIRouter(prefix="/api")

CHECK_TIMEOUT_SECONDS = 3


async def _check(probe) -> str:
    try:
        await asyncio.wait_for(probe(), CHECK_TIMEOUT_SECONDS)
        return "ok"
    except Exception as exc:  # noqa: BLE001 - any failure is reported, not raised
        return f"{type(exc).__name__}: {str(exc)[:160]}"


async def _ping_mongo() -> None:
    from app.models.job import Job

    await Job.get_pymongo_collection().database.command("ping")


async def _ping_render() -> None:
    from app.render.client import check_health

    await check_health()


@router.get("/health", response_model=Health)
async def health(request: Request) -> Health:
    mongo, render = await asyncio.gather(_check(_ping_mongo), _check(_ping_render))
    runner = getattr(request.app.state, "runner", None)
    pipeline = (
        "ok"
        if runner is not None
        else getattr(request.app.state, "setup_error", None) or "not started"
    )
    return Health(
        status="ok" if mongo == render == pipeline == "ok" else "degraded",
        mongo=mongo,
        render=render,
        pipeline=pipeline,
        tts=f"{settings.tts_provider}: {settings.tts_voice}",
    )
