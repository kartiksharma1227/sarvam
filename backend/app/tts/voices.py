"""Narrator voices a video can use (Edge neural voices, all checked to give word timings)."""

from app.config import settings

VOICES: list[dict] = [
    {"id": "en-US-AndrewNeural", "label": "Andrew", "accent": "US", "gender": "male"},
    {"id": "en-US-AvaNeural", "label": "Ava", "accent": "US", "gender": "female"},
    {"id": "en-US-BrianNeural", "label": "Brian", "accent": "US", "gender": "male"},
    {"id": "en-US-EmmaNeural", "label": "Emma", "accent": "US", "gender": "female"},
    {"id": "en-GB-RyanNeural", "label": "Ryan", "accent": "UK", "gender": "male"},
    {"id": "en-GB-SoniaNeural", "label": "Sonia", "accent": "UK", "gender": "female"},
    {
        "id": "en-IN-PrabhatNeural",
        "label": "Prabhat",
        "accent": "India",
        "gender": "male",
    },
    {
        "id": "en-IN-NeerjaNeural",
        "label": "Neerja",
        "accent": "India",
        "gender": "female",
    },
]
VOICE_IDS = {v["id"] for v in VOICES}

# Read aloud by the "preview" button in the app.
SAMPLE_TEXT = (
    "Hi! I'll narrate your explainer, and every drawing appears right as I say it."
)


def default_voice() -> str:
    return settings.tts_voice


def voice_label(voice_id: str) -> str:
    """e.g. "Ava (US)"; unknown ids are shown as they are."""
    v = next((v for v in VOICES if v["id"] == voice_id), None)
    return f"{v['label']} ({v['accent']})" if v else voice_id


def is_allowed(voice_id: str) -> bool:
    return voice_id in VOICE_IDS or voice_id == default_voice()
