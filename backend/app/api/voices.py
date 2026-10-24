"""Narrator voices: the list for the prompt box, and a short cached preview of each."""

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse

from app.config import settings
from app.tts.base import get_provider, synthesize_cached
from app.tts.voices import SAMPLE_TEXT, VOICE_IDS, VOICES, default_voice

router = APIRouter(prefix="/api/voices", tags=["voices"])


@router.get("")
async def list_voices() -> dict:
    return {"default": default_voice(), "voices": VOICES}


@router.get("/{voice_id}/sample")
async def voice_sample(voice_id: str) -> FileResponse:
    """A one-line preview, synthesised on first request and cached under media/voices/."""
    if voice_id not in VOICE_IDS:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"No voice {voice_id}")
    out = settings.media_dir.resolve() / "voices" / f"{voice_id}.mp3"
    try:
        await synthesize_cached(get_provider(), SAMPLE_TEXT, out, voice=voice_id)
    except Exception as exc:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, detail=f"Voice service unavailable: {exc}"
        ) from exc
    return FileResponse(out, media_type="audio/mpeg")
