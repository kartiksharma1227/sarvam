"""The signed-in user's own account: quota, usage, display name and password."""

from datetime import timedelta

from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel, Field

from app.api.auth import _limit
from app.auth import (
    QUOTA_WINDOW_DAYS,
    CurrentUser,
    hash_password,
    quota,
    set_session,
    verify_password,
)
from app.models.account import VideoStart
from app.models.job import Job, now
from app.pricing import job_cost
from app.schemas.api import Quota

router = APIRouter(prefix="/api/account", tags=["account"])


class ProfileUpdate(BaseModel):
    name: str = Field(max_length=60)


class PasswordChange(BaseModel):
    current_password: str = Field(max_length=200)
    new_password: str = Field(min_length=8, max_length=200)


@router.get("/quota", response_model=Quota)
async def get_quota(user: CurrentUser) -> Quota:
    return Quota(**await quota(user))


@router.get("/usage")
async def usage(user: CurrentUser) -> dict:
    """Videos made (all time and the last 30 days, with each start time for a per-day chart)
    and what their AI calls cost."""
    since = now() - timedelta(days=QUOTA_WINDOW_DAYS)
    starts = (
        await VideoStart.find({"owner_id": user.id, "created_at": {"$gte": since}})
        .sort("+created_at")
        .to_list()
    )
    cursor = Job.get_pymongo_collection().find(
        {"owner_id": user.id, "usage": {"$exists": True}}, {"usage": 1}
    )
    cost = sum(job_cost(doc["usage"])["total_usd"] for doc in await cursor.to_list())
    return {
        "videos_total": await VideoStart.find({"owner_id": user.id}).count(),
        "videos_window": len(starts),
        "window_days": QUOTA_WINDOW_DAYS,
        "starts": [s.created_at for s in starts],
        "ai_cost_usd": round(cost, 2),
    }


@router.patch("")
async def update_profile(body: ProfileUpdate, user: CurrentUser) -> dict:
    user.name = body.name.strip()
    await user.set({"name": user.name})
    return user.public()


@router.post("/password")
async def change_password(
    body: PasswordChange, request: Request, response: Response, user: CurrentUser
) -> dict:
    """Change the password; every other browser is logged out, this one stays signed in."""
    _limit(request, f"password|{user.email}")
    if not verify_password(user.password_hash, body.current_password):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail="Your current password isn't right."
        )
    user.password_hash = hash_password(body.new_password)
    user.session_version += 1
    await user.set(
        {"password_hash": user.password_hash, "session_version": user.session_version}
    )
    set_session(response, user)
    return user.public()
