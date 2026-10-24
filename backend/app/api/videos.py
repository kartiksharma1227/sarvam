"""Gallery: finished videos, newest first. Plus one public showcase video for the landing page."""

from fastapi import APIRouter, Query

from app.api.jobs import media_url
from app.auth import CurrentUser, owner_filter
from app.models.user import User
from app.models.video import Video
from app.schemas.api import VideoSummary

router = APIRouter(tags=["videos"])


def summary(v: Video) -> VideoSummary:
    return VideoSummary(
        id=str(v.id),
        job_id=str(v.job_id),
        title=v.title,
        topic=v.topic,
        duration=v.duration,
        aspect=v.aspect,
        video_url=media_url(v.final_video_path),
        thumbnail_url=media_url(v.thumbnail_path),
        created_at=v.created_at,
    )


@router.get("/api/videos", response_model=list[VideoSummary])
async def list_videos(
    user: CurrentUser, limit: int = Query(100, ge=1, le=500)
) -> list[VideoSummary]:
    videos = (
        await Video.find(owner_filter(user)).sort("-created_at").limit(limit).to_list()
    )
    return [summary(v) for v in videos]


@router.get("/api/showcase", response_model=VideoSummary | None)
async def showcase() -> VideoSummary | None:
    """Public: the admin's newest video, shown on the landing page (None if there is none)."""
    admins = [u.id for u in await User.find(User.is_admin == True).to_list()]
    if not admins:
        return None
    video = (
        await Video.find({"owner_id": {"$in": admins}})
        .sort("-created_at")
        .first_or_none()
    )
    return summary(video) if video else None
