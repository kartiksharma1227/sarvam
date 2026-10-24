"""Sarvam Bulbul narration for the existing pipeline (a TTSProvider, see backend/app/tts/base.py).

Voice ids look like `sarvam:<lang>:<speaker>`. The scriptwriter writes English; this provider
translates each scene's narration into the job's language, then speaks it. Bulbul gives no word
timings, so words are spread over the audio by length; the English cue phrases then don't match
and `resolve_cues` spaces the drawings evenly (no renderer change needed).
"""

import asyncio
import logging
from pathlib import Path

import sarvam
from app.ffmpeg import probe_duration
from app.tts.base import TTSResult, Word

log = logging.getLogger("sarvam.tts")

LEAD_IN = 0.15


def parse_voice(voice: str) -> tuple[str, str]:
    _, lang, speaker = voice.split(":", 2)
    return lang, speaker


def make_voice(lang: str, speaker: str | None = None) -> str:
    return f"sarvam:{lang}:{speaker or sarvam.lang_info(lang)['speaker']}"


def spread_words(text: str, duration: float) -> list[Word]:
    tokens = text.split()
    if not tokens:
        return []
    span = max(0.1, duration - LEAD_IN)
    total = sum(len(t) for t in tokens)
    t, words = LEAD_IN, []
    for tok in tokens:
        d = span * len(tok) / total
        words.append(Word(text=tok, start=round(t, 3), end=round(t + d, 3)))
        t += d
    return words


class SarvamTTS:
    name = "sarvam"

    def __init__(self, voice: str = "sarvam:hi-IN:shubh"):
        self.voice = voice

    async def synthesize(self, text: str, out_path: Path, voice: str | None = None) -> TTSResult:
        lang, speaker = parse_voice(voice or self.voice)
        spoken = await sarvam.translate(text, lang) if lang != "en-IN" else text
        log.info("Narration (%s): %s", lang, spoken[:120])
        wavs = await sarvam.tts(spoken, lang, speaker)
        await sarvam.wavs_to_file(wavs, out_path)
        duration = await asyncio.to_thread(probe_duration, out_path)
        # Keep the spoken text next to the audio (handy for captions / debugging).
        out_path.with_suffix(".txt").write_text(spoken, encoding="utf-8")
        return TTSResult(audio_path=out_path, duration=duration, words=spread_words(spoken, duration))


class RoutedTTS:
    """`sarvam:*` voices go to Sarvam, everything else to the original (Edge) provider."""

    name = "routed"

    def __init__(self, edge):
        self.edge = edge
        self.sarvam = SarvamTTS()
        self.voice = edge.voice

    async def synthesize(self, text: str, out_path: Path, voice: str | None = None) -> TTSResult:
        voice = voice or self.voice
        if voice.startswith("sarvam:"):
            return await self.sarvam.synthesize(text, out_path, voice)
        return await self.edge.synthesize(text, out_path, voice)
