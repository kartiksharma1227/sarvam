"""Accounts: password hashing, the session cookie, the current user, and a login attempt limiter.

Sessions are signed JWTs in an httpOnly cookie, so the browser sends them with every same-origin
request (including EventSource streams) and page scripts can't read them.
"""

import logging
import secrets
import time
from collections import defaultdict, deque
from datetime import timedelta
from typing import Annotated

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from beanie import PydanticObjectId
from fastapi import Depends, HTTPException, Request, Response, status

from app.billing.plans import effective_plan
from app.config import settings
from app.models.account import VideoStart
from app.models.job import Job, now
from app.models.user import User

log = logging.getLogger(__name__)

COOKIE = "mindsketch_session"
_hasher = PasswordHasher()
_fallback_secret: str | None = None


def _secret() -> str:
    global _fallback_secret
    if settings.auth_secret:
        return settings.auth_secret
    if _fallback_secret is None:
        log.warning(
            "AUTH_SECRET is not set: using a random one (everyone is logged out on restart)"
        )
        _fallback_secret = secrets.token_urlsafe(48)
    return _fallback_secret


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


def make_token(user: User) -> str:
    expires = now() + timedelta(days=settings.session_days)
    return jwt.encode(
        {"sub": str(user.id), "v": user.session_version, "exp": expires},
        _secret(),
        algorithm="HS256",
    )


def read_token(token: str) -> tuple[str, int] | None:
    """(user id, session version), or None if the token is invalid or expired."""
    try:
        claims = jwt.decode(token, _secret(), algorithms=["HS256"])
    except jwt.PyJWTError:
        return None
    return claims["sub"], claims.get("v", 0)


def set_session(response: Response, user: User) -> None:
    response.set_cookie(
        COOKIE,
        make_token(user),
        max_age=settings.session_days * 24 * 3600,
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
        path="/",
    )


def clear_session(response: Response) -> None:
    response.delete_cookie(COOKIE, path="/")


async def optional_user(request: Request) -> User | None:
    token = request.cookies.get(COOKIE)
    claims = read_token(token) if token else None
    if not claims:
        return None
    user_id, version = claims
    try:
        user = await User.get(PydanticObjectId(user_id))
    except Exception:  # noqa: BLE001 - a malformed id in a valid token: treat as logged out
        return None
    # A password change ends every session started before it.
    if user is None or user.session_version != version:
        return None
    return user


OptionalUser = Annotated[User | None, Depends(optional_user)]


async def current_user(user: OptionalUser) -> User:
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Please log in")
    return user


# Use as a parameter type: `user: CurrentUser` (401 when not logged in).
CurrentUser = Annotated[User, Depends(current_user)]


# ---- who sees what


def owner_filter(user: User) -> dict:
    """Mongo filter for the jobs/videos a user may see: their own; admins also see unowned ones."""
    if user.is_admin:
        return {"$or": [{"owner_id": user.id}, {"owner_id": None}]}
    return {"owner_id": user.id}


def can_see(user: User, owner_id) -> bool:
    return owner_id == user.id or (user.is_admin and owner_id is None)


# ---- rate limits

QUOTA_WINDOW_DAYS = 30


def _fmt_wait(seconds: float) -> str:
    minutes = max(1, int(seconds // 60))
    hours, minutes = divmod(minutes, 60)
    days, hours = divmod(hours, 24)
    if days:
        return f"{days}d {hours}h"
    return f"{hours}h {minutes}m" if hours else f"{minutes}m"


def unlimited(user: User) -> bool:
    return user.is_admin and settings.admin_unlimited


async def quota(user: User) -> dict:
    """How many videos this user may still start: their plan's allowance over a rolling 30 days.

    Each video uses its slot for 30 days after it was started, even if it is deleted.
    """
    plan = effective_plan(user)
    active = await Job.find(
        {"owner_id": user.id, "status": {"$in": ["queued", "running"]}}
    ).count()
    window_start = now() - timedelta(days=QUOTA_WINDOW_DAYS)
    starts = (
        await VideoStart.find(
            {"owner_id": user.id, "created_at": {"$gte": window_start}}
        )
        .sort("+created_at")
        .to_list()
    )
    used, limit = len(starts), plan.monthly_videos
    # When the oldest start in the window leaves it, one more video is allowed.
    next_free_at = (
        starts[0].created_at + timedelta(days=QUOTA_WINDOW_DAYS) if starts else None
    )
    return {
        "unlimited": unlimited(user),
        "plan": plan.id,
        "plan_name": plan.name,
        "plan_expires_at": user.plan_expires_at if plan.price_inr else None,
        "limit": limit,
        "used": used,
        "remaining": max(0, limit - used),
        "window_days": QUOTA_WINDOW_DAYS,
        "next_free_at": next_free_at,
        "active": active,
        "max_active": plan.max_active,
    }


async def check_video_limits(user: User) -> None:
    """429 if this user may not start another video now."""
    if unlimited(user):
        return
    q = await quota(user)
    if q["active"] >= q["max_active"]:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"You already have {q['active']} video(s) in progress, the most your "
            f"{q['plan_name']} plan allows at once; wait for one to finish.",
        )
    if q["remaining"] == 0:
        wait = (q["next_free_at"] - now()).total_seconds()
        upgrade = " Upgrade your plan for more." if q["plan"] != "max" else ""
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"You've used all {q['limit']} videos of your {q['plan_name']} plan this month; "
            f"next one in {_fmt_wait(wait)}.{upgrade}",
        )


class AttemptLimiter:
    """At most `limit` attempts per key in a sliding `window` of seconds (in memory, per process)."""

    def __init__(self, limit: int = 10, window: float = 15 * 60):
        self.limit, self.window = limit, window
        self._hits: dict[str, deque] = defaultdict(deque)

    def hit(self, key: str) -> bool:
        """Record an attempt; False if the key is over its limit."""
        t = time.monotonic()
        hits = self._hits[key]
        while hits and t - hits[0] > self.window:
            hits.popleft()
        if len(hits) >= self.limit:
            return False
        hits.append(t)
        return True

    def reset(self, key: str) -> None:
        self._hits.pop(key, None)


login_attempts = AttemptLimiter()
