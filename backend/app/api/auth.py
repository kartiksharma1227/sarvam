"""Sign up, log in, log out, who am I, and resetting a forgotten password."""

import hashlib
import html
import logging
import re
import secrets
from datetime import timedelta

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, Response, status
from pydantic import BaseModel, Field, field_validator
from pymongo.errors import DuplicateKeyError

from app.auth import (
    AttemptLimiter,
    CurrentUser,
    clear_session,
    hash_password,
    login_attempts,
    set_session,
    verify_password,
)
from app.config import settings
from app.mailer import MailError, send_email
from app.models.account import PasswordReset
from app.models.job import Job, now
from app.models.user import User
from app.models.video import Video

router = APIRouter(prefix="/api/auth", tags=["auth"])
log = logging.getLogger(__name__)

EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class EmailOnly(BaseModel):
    email: str = Field(max_length=254)

    @field_validator("email")
    @classmethod
    def _email(cls, value: str) -> str:
        value = value.strip().lower()
        if not EMAIL.match(value):
            raise ValueError("enter a valid email address")
        return value


class Credentials(EmailOnly):
    password: str = Field(min_length=8, max_length=200)


class Signup(Credentials):
    name: str = Field(default="", max_length=60)


class ResetPassword(BaseModel):
    token: str = Field(min_length=20, max_length=200)
    password: str = Field(min_length=8, max_length=200)


# Reset emails: a few per address and browser per hour, so the form can't be used to spam someone.
reset_requests = AttemptLimiter(limit=5, window=60 * 60)


def _limit(
    request: Request, email: str, limiter: AttemptLimiter = login_attempts
) -> str:
    key = f"{request.client.host if request.client else '?'}|{email}"
    if not limiter.hit(key):
        minutes = int(limiter.window // 60)
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Too many attempts. Try again in {minutes} minutes.",
        )
    return key


@router.post("/signup", status_code=status.HTTP_201_CREATED)
async def signup(body: Signup, request: Request, response: Response) -> dict:
    key = _limit(request, body.email)
    # The first account is the admin and takes over everything made before accounts existed.
    first = await User.count() == 0
    user = User(
        email=body.email,
        name=body.name.strip(),
        password_hash=hash_password(body.password),
        is_admin=first,
    )
    try:
        await user.insert()
    except DuplicateKeyError as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail="An account with this email already exists"
        ) from exc
    login_attempts.reset(key)
    if first:
        await Job.find({"owner_id": None}).update({"$set": {"owner_id": user.id}})
        await Video.find({"owner_id": None}).update({"$set": {"owner_id": user.id}})
    set_session(response, user)
    return user.public()


@router.post("/login")
async def login(body: Credentials, request: Request, response: Response) -> dict:
    key = _limit(request, body.email)
    user = await User.find_one(User.email == body.email)
    if user is None or not verify_password(user.password_hash, body.password):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, detail="Wrong email or password"
        )
    login_attempts.reset(key)
    set_session(response, user)
    return user.public()


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(response: Response) -> Response:
    clear_session(response)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.get("/me")
async def me(user: CurrentUser) -> dict:
    return user.public()


# ---- forgotten password

FORGOT_REPLY = (
    "If an account exists for that email, a reset link is on its way. Check your inbox."
)
INVALID_LINK = "This reset link is invalid, used or expired. Ask for a new one."


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def reset_email(user: User, link: str) -> tuple[str, str, str]:
    """(subject, text, html) of the reset email."""
    minutes = settings.password_reset_minutes
    hello = f"Hi {user.name}," if user.name else "Hi,"
    subject = "Reset your Mindsketch.ai password"
    text = (
        f"{hello}\n\n"
        f"Someone (hopefully you) asked to reset the password for your Mindsketch.ai account "
        f"({user.email}).\n\n"
        f"Choose a new password here. The link works once, for {minutes} minutes:\n{link}\n\n"
        "If you didn't ask for this, ignore this email: your password stays the same.\n"
    )
    page = f"""\
<div style="font-family:Arial,sans-serif;font-size:16px;color:#1f1d1a;max-width:480px">
  <p>{html.escape(hello)}</p>
  <p>Someone (hopefully you) asked to reset the password for your Mindsketch.ai account
  ({html.escape(user.email)}).</p>
  <p><a href="{html.escape(link)}" style="display:inline-block;padding:10px 22px;background:#f5c518;
  color:#1f1d1a;border:2px solid #1f1d1a;border-radius:999px;text-decoration:none">Choose a new password</a></p>
  <p style="color:#6b665e;font-size:14px">The link works once, for {minutes} minutes.
  If you didn't ask for this, ignore this email: your password stays the same.</p>
</div>"""
    return subject, text, page


async def send_reset_link(user: User) -> None:
    """Make a fresh one-time token (older unused ones stop working) and email the link."""
    token = secrets.token_urlsafe(32)
    await PasswordReset.find({"user_id": user.id, "used_at": None}).delete()
    await PasswordReset(
        user_id=user.id,
        token_hash=_hash_token(token),
        expires_at=now() + timedelta(minutes=settings.password_reset_minutes),
    ).insert()
    link = f"{settings.app_base_url.rstrip('/')}/reset-password?token={token}"
    try:
        await send_email(user.email, *reset_email(user, link))
    except MailError as exc:
        log.error("Could not send the reset email to %s: %s", user.email, exc)


@router.post("/forgot", status_code=status.HTTP_202_ACCEPTED)
async def forgot_password(
    body: EmailOnly, request: Request, background: BackgroundTasks
) -> dict:
    """Email a reset link. The reply is the same whether or not the account exists."""
    _limit(request, body.email, reset_requests)
    user = await User.find_one(User.email == body.email)
    if user is not None:
        background.add_task(
            send_reset_link, user
        )  # after replying, so timing reveals nothing
    return {"detail": FORGOT_REPLY}


@router.post("/reset")
async def reset_password(
    body: ResetPassword, request: Request, response: Response
) -> dict:
    """Set a new password with a reset link's token, end all other sessions, and log in."""
    _limit(request, "reset-password")
    claimed = await PasswordReset.get_pymongo_collection().find_one_and_update(
        {
            "token_hash": _hash_token(body.token),
            "used_at": None,
            "expires_at": {"$gt": now()},
        },
        {"$set": {"used_at": now()}},
    )
    user = await User.get(claimed["user_id"]) if claimed else None
    if user is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=INVALID_LINK)
    user.password_hash = hash_password(body.password)
    user.session_version += 1
    # Only these fields: a membership could be applied to the account at the same moment.
    await user.set(
        {"password_hash": user.password_hash, "session_version": user.session_version}
    )
    await PasswordReset.find({"user_id": user.id, "used_at": None}).delete()
    set_session(response, user)
    return user.public()
