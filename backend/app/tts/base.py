"""Text-to-speech interface shared by every provider."""

import json
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel


class Word(BaseModel):
    text: str
    start: float  # seconds
    end: float


class TTSResult(BaseModel):
    audio_path: Path
    duration: float
    words: list[Word]


class TTSProvider(Protocol):
    name: str
    voice: str

    async def synthesize(
        self, text: str, out_path: Path, voice: str | None = None
    ) -> TTSResult: ...


async def synthesize_cached(
    provider: TTSProvider, text: str, out_path: Path, voice: str | None = None
) -> TTSResult:
    """Synthesize once; reuse the audio + word timings when the same text and voice were done before.

    `voice` overrides the provider's default voice (each video can pick its narrator).
    """
    voice = voice or provider.voice
    sidecar = out_path.with_suffix(".json")
    key = {"provider": provider.name, "voice": voice, "text": text}
    if out_path.exists() and sidecar.exists():
        cached = json.loads(sidecar.read_text())
        if cached.get("key") == key:
            return TTSResult.model_validate(cached["result"])

    out_path.parent.mkdir(parents=True, exist_ok=True)
    result = await provider.synthesize(text, out_path, voice=voice)
    sidecar.write_text(
        json.dumps({"key": key, "result": result.model_dump(mode="json")}, indent=2)
    )
    return result


def get_provider() -> TTSProvider:
    from app.config import settings

    if settings.tts_provider == "edge":
        from app.tts.edge import EdgeTTS

        return EdgeTTS(voice=settings.tts_voice, proxy=settings.tts_proxy)
    raise ValueError(
        f"Unsupported TTS_PROVIDER {settings.tts_provider!r} (available: edge)"
    )
