"""An account (collection `users`). The first account to sign up is the admin."""

from datetime import datetime
from typing import Annotated, Literal

from beanie import Document, Indexed
from pydantic import Field

from app.models.job import now


class User(Document):
    email: Annotated[str, Indexed(unique=True)]  # stored lowercased
    name: str = ""
    password_hash: str
    is_admin: bool = False
    # Bumped when the password changes: login cookies carrying an older number stop working.
    session_version: int = 0
    # Membership (app/billing/plans.py): a paid plan lasts until plan_expires_at, then it's Free again.
    plan: Literal["free", "pro", "max"] = "free"
    plan_expires_at: datetime | None = None
    created_at: datetime = Field(default_factory=now)

    class Settings:
        name = "users"

    def public(self) -> dict:
        from app.billing.plans import effective_plan

        plan = effective_plan(self)
        return {
            "id": str(self.id),
            "email": self.email,
            "name": self.name,
            "is_admin": self.is_admin,
            "plan": plan.id,
            "plan_name": plan.name,
            "plan_expires_at": self.plan_expires_at if plan.price_inr else None,
            "created_at": self.created_at,
        }
