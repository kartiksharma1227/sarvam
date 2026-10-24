"""A video generation job and its checkpoints (collection `jobs`)."""

from datetime import UTC, datetime
from typing import Literal

from beanie import Document, PydanticObjectId
from pydantic import BaseModel, Field

from app.schemas.plan import LessonPlan
from app.schemas.script import Script
from app.tts.base import Word

JobStatus = Literal["queued", "running", "completed", "failed"]
# A scene moves through these in order; each one is saved as soon as it is reached.
SceneStatus = Literal[
    "pending", "designed", "narrated", "icons", "rendered", "streamed"
]
SCENE_STEPS: tuple[str, ...] = SceneStatus.__args__


def now() -> datetime:
    return datetime.now(UTC)


def _default_voice() -> str:
    from app.tts.voices import default_voice

    return default_voice()


class JobOptions(BaseModel):
    background: Literal["plain", "graph_paper"] = "plain"
    aspect: Literal["16:9", "9:16"] = "16:9"  # 9:16 = vertical video
    voice: str = Field(default_factory=_default_voice)  # narrator (app/tts/voices.py)


class Segment(BaseModel):
    uri: str  # relative to the job's hls/ folder
    duration: float


class SceneState(BaseModel):
    """Per-scene progress. Paths are relative to MEDIA_DIR."""

    id: str
    index: int
    status: SceneStatus = "pending"
    error: str | None = None
    spec: dict | None = None  # {id, title, narration, layout, slots}
    audio_path: str | None = None
    duration: float | None = None
    words: list[Word] = Field(default_factory=list)
    cues: list[dict] = Field(
        default_factory=list
    )  # {target, phrase, start, method, matched}
    icon_map: dict[str, str] = Field(
        default_factory=dict
    )  # icon_query -> "icons/<name>.svg"
    render_path: str | None = None
    segments: list[Segment] = Field(default_factory=list)  # HLS pieces of render_path

    def step(self) -> int:
        """How many steps are done (0 = pending, 5 = streamed)."""
        return SCENE_STEPS.index(self.status)


class IconChoice(BaseModel):
    name: str
    how: Literal["exact", "reranked", "generated", "fallback"]


class JobError(BaseModel):
    stage: str
    message: str


class Job(Document):
    topic: str
    owner_id: PydanticObjectId | None = (
        None  # the account that made it (None: CLI, before accounts)
    )
    options: JobOptions = Field(default_factory=JobOptions)
    status: JobStatus = "queued"
    stage: str = "queued"
    progress: float = 0.0

    plan: LessonPlan | None = None
    draft_script: Script | None = None  # scriptwriter output
    script: Script | None = None  # after the editor
    scenes: list[SceneState] = Field(default_factory=list)
    # Icon picks for the whole video, so a concept looks the same in every scene.
    icon_choices: dict[str, IconChoice] = Field(
        default_factory=dict
    )  # normalised query -> pick
    icons_generated: list[str] = Field(
        default_factory=list
    )  # names drawn for this video

    playlist_path: str | None = None  # live HLS stream, relative to MEDIA_DIR
    final_video_path: str | None = None
    thumbnail_path: str | None = None
    duration: float | None = None

    error: JobError | None = None
    usage: dict = Field(default_factory=dict)
    models: dict[str, str] = Field(default_factory=dict)
    attempts: int = 0

    heartbeat_at: datetime = Field(default_factory=now)  # last progress (watchdog)
    alive_at: datetime = Field(
        default_factory=now
    )  # last tick from the running process
    created_at: datetime = Field(default_factory=now)
    updated_at: datetime = Field(default_factory=now)

    class Settings:
        name = "jobs"
