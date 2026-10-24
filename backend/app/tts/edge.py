"""Free Microsoft Edge TTS with per-word timestamps."""

import asyncio
import os
from pathlib import Path

import aiohttp
import edge_tts
from edge_tts.exceptions import EdgeTTSException
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.ffmpeg import probe_duration
from app.tts.base import TTSResult, Word

TICKS_PER_SECOND = 10_000_000  # edge-tts offsets/durations are in 100-ns units
TIMEOUT_SECONDS = 60


def words_from_boundaries(events: list[dict]) -> list[Word]:
    return [
        Word(
            text=e["text"],
            start=e["offset"] / TICKS_PER_SECOND,
            end=(e["offset"] + e["duration"]) / TICKS_PER_SECOND,
        )
        for e in events
        if e.get("type") == "WordBoundary"
    ]


class EdgeTTS:
    name = "edge"

    def __init__(self, voice: str, proxy: str | None = None):
        self.voice = voice
        # aiohttp (used by edge-tts) ignores proxy env vars, so pass the proxy explicitly.
        self.proxy = (
            proxy or os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
        )

    # The voice service occasionally drops a request (seen through proxies as "No audio was received").
    @retry(
        retry=retry_if_exception_type(
            (EdgeTTSException, aiohttp.ClientError, TimeoutError)
        ),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, max=10),
        reraise=True,
    )
    async def synthesize(
        self, text: str, out_path: Path, voice: str | None = None
    ) -> TTSResult:
        return await asyncio.wait_for(
            self._synthesize(text, out_path, voice or self.voice), TIMEOUT_SECONDS
        )

    async def _synthesize(self, text: str, out_path: Path, voice: str) -> TTSResult:
        # Newer edge-tts versions default to sentence boundaries; word timings must be requested.
        communicate = edge_tts.Communicate(
            text, voice, boundary="WordBoundary", proxy=self.proxy
        )
        audio = bytearray()
        events: list[dict] = []
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio.extend(chunk["data"])
            else:
                events.append(chunk)
        if not audio:
            raise RuntimeError("edge-tts returned no audio")

        out_path.write_bytes(audio)
        duration = await asyncio.to_thread(probe_duration, out_path)
        return TTSResult(
            audio_path=out_path, duration=duration, words=words_from_boundaries(events)
        )
