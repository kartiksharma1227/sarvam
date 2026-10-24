"""Client for the Node render service (renderer/server/render-server.js)."""

from pathlib import Path

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.config import settings

RENDER_TIMEOUT_SECONDS = 300


class RenderServiceError(RuntimeError):
    pass


def _client(timeout: float) -> httpx.AsyncClient:
    # The service is local; never route it through the user's HTTP proxy.
    return httpx.AsyncClient(
        base_url=settings.render_service_url, timeout=timeout, trust_env=False
    )


async def check_health() -> dict:
    try:
        async with _client(5) as client:
            response = await client.get("/health")
            response.raise_for_status()
            return response.json()
    except httpx.HTTPError as exc:
        raise RenderServiceError(
            f"Render service not reachable at {settings.render_service_url} ({exc}). "
            "Start it with: cd renderer && npm run server"
        ) from exc


# Only failed connections are retried (not timeouts: a slow render would just take twice as long).
# A render that ran and failed is reported, not hidden.
@retry(
    retry=retry_if_exception_type((httpx.ConnectError, httpx.RemoteProtocolError)),
    stop=stop_after_attempt(2),
    wait=wait_exponential(multiplier=2, max=10),
    reraise=True,
)
async def render_scene(props: dict, out_path: Path) -> dict:
    """Render one scene to `out_path` (absolute). Returns {outPath, durationInFrames, fps}."""
    async with _client(RENDER_TIMEOUT_SECONDS) as client:
        response = await client.post(
            "/render", json={"props": props, "outPath": str(out_path.resolve())}
        )
    if response.status_code != 200:
        raise RenderServiceError(
            f"Render of {props['scene']['id']} failed: {response.text}"
        )
    return response.json()
