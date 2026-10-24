"""Request and response bodies for the HTTP API."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class JobCreate(BaseModel):
    topic: str = Field(min_length=3, max_length=300)
    background: Literal["plain", "graph_paper"] = "plain"
    aspect: Literal["16:9", "9:16"] = "16:9"
    voice: str | None = None  # one of GET /api/voices; None = the default narrator

    @field_validator("voice")
    @classmethod
    def _known_voice(cls, voice: str | None) -> str | None:
        from app.tts.voices import is_allowed

        if voice is not None and not is_allowed(voice):
            raise ValueError(f"unknown voice {voice!r}; see GET /api/voices")
        return voice


class JobCreated(BaseModel):
    job_id: str


class SceneSnapshot(BaseModel):
    id: str
    index: int
    status: str
    title: str | None = None
    layout: str | None = None
    error: str | None = None


class JobSnapshot(BaseModel):
    id: str
    topic: str
    status: str
    stage: str
    progress: float
    attempts: int
    title: str | None = None
    options: dict
    voice: str  # e.g. "edge: en-US-AndrewNeural", for the "narrated by" line
    scene_count: int
    scenes: list[SceneSnapshot]
    playlist_url: str | None = None  # live HLS stream (grows while scenes render)
    video_url: str | None = None
    thumbnail_url: str | None = None
    duration: float | None = None
    cost_usd: float | None = (
        None  # estimated, from recorded token usage (app/pricing.py)
    )
    error: dict | None = None
    created_at: datetime
    updated_at: datetime


class JobSummary(BaseModel):
    """One row of the sidebar history."""

    id: str
    topic: str
    title: str | None = None
    status: str
    stage: str
    progress: float
    thumbnail_url: str | None = None
    cost_usd: float | None = None
    created_at: datetime


class VideoSummary(BaseModel):
    id: str
    job_id: str
    title: str
    topic: str
    duration: float
    aspect: str = "16:9"
    video_url: str
    thumbnail_url: str | None = None
    created_at: datetime


class Health(BaseModel):
    status: Literal["ok", "degraded"]
    mongo: str  # "ok" or what went wrong
    render: str
    pipeline: str
    tts: str


class Quota(BaseModel):
    """Videos left in the rolling 30 days on the user's plan (the admin may be unlimited)."""

    unlimited: bool
    plan: str  # free | pro | max (what applies now: an expired pass counts as free)
    plan_name: str
    plan_expires_at: datetime | None = None
    limit: int
    used: int
    remaining: int
    window_days: int
    next_free_at: datetime | None = (
        None  # when the oldest video in the window stops counting
    )
    active: int  # videos in progress now
    max_active: int
