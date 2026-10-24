"""Account records: video starts (for the daily quota) and password reset tokens."""

from datetime import datetime
from typing import ClassVar

from beanie import Document, PydanticObjectId
from pydantic import Field
from pymongo import ASCENDING, IndexModel

from app.models.job import now


class VideoStart(Document):
    """One row per video a user started (collection `video_starts`).

    The daily quota counts these, not jobs, so deleting a video doesn't hand its slot back.
    """

    owner_id: PydanticObjectId
    job_id: PydanticObjectId
    created_at: datetime = Field(default_factory=now)

    class Settings:
        name = "video_starts"
        indexes: ClassVar = [
            IndexModel([("owner_id", ASCENDING), ("created_at", ASCENDING)])
        ]


class PasswordReset(Document):
    """A one-time reset link (collection `password_resets`). Only the token's hash is stored."""

    user_id: PydanticObjectId
    token_hash: str
    expires_at: datetime
    used_at: datetime | None = None
    created_at: datetime = Field(default_factory=now)

    class Settings:
        name = "password_resets"
        indexes: ClassVar = [
            IndexModel([("token_hash", ASCENDING)], unique=True),
            # MongoDB removes a reset record a day after it expires.
            IndexModel([("expires_at", ASCENDING)], expireAfterSeconds=24 * 3600),
        ]
