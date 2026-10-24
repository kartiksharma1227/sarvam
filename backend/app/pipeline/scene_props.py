"""Assemble the RenderProps the renderer expects from a scene spec plus its narration."""

from app.pipeline.timing import CueResult, cues_for_scene
from app.tts.base import TTSResult

# Silence before narration starts, so the scene title draws first.
AUDIO_LEAD_IN = 0.5


def build_render_props(
    base: dict, tts: TTSResult, audio_url: str
) -> tuple[dict, list[CueResult]]:
    """`base` holds scene, icons and options. Returns (props, cues) with cues shifted by the lead-in."""
    scene = base["scene"]
    cues = cues_for_scene(scene["layout"], scene["slots"], tts.words, tts.duration)
    props = {
        **{k: v for k, v in base.items() if k not in ("duration", "cues", "audio")},
        "audio": {"url": audio_url, "duration": tts.duration, "offset": AUDIO_LEAD_IN},
        "cues": [
            {"target": c.target, "start": round(c.start + AUDIO_LEAD_IN, 3)}
            for c in cues
        ],
    }
    return props, cues
