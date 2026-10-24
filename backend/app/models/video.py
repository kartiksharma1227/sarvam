"""A finished video for the gallery (collection `videos`)."""

from datetime import datetime

from beanie import Document, PydanticObjectId
from pydantic import Field

from app.models.job import now


class Video(Document):
    job_id: PydanticObjectId
    owner_id: PydanticObjectId | None = None
    title: str
    topic: str
    duration: float
    aspect: str = "16:9"  # "9:16" = vertical
    final_video_path: str  # relative to MEDIA_DIR
    thumbnail_path: str | None = None
    created_at: datetime = Field(default_factory=now)

    class Settings:
        name = "videos"
