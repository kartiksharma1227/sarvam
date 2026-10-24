"""Builds the real pipeline dependencies (OpenAI, voice, icon library, render service)."""

import logging

from app.config import settings
from app.pipeline.orchestrator import Deps

log = logging.getLogger(__name__)


async def build_deps(media_base_url: str) -> Deps:
    from app.agents.llm import get_llm
    from app.icons.embed import OpenAIEmbedder
    from app.icons.generate import ImageGenerator
    from app.icons.library import IconLibrary
    from app.render.client import RenderServiceError, check_health
    from app.tts.base import get_provider

    llm = get_llm()  # raises AgentError with a clear message if the key is missing
    media_root = settings.media_dir.resolve()
    try:
        # Match the render service's own concurrency, so requests never wait in its queue.
        render_concurrency = int((await check_health())["concurrency"])
    except (RenderServiceError, KeyError, ValueError) as exc:
        log.warning(
            "Render service: %s; assuming %d slots", exc, settings.render_concurrency
        )
        render_concurrency = settings.render_concurrency
    return Deps(
        llm=llm,
        tts=get_provider(),
        media_root=media_root,
        media_base_url=media_base_url,
        icons=IconLibrary(llm, OpenAIEmbedder(), ImageGenerator(), media_root),
        render_concurrency=render_concurrency,
    )
