"""The membership plans. A paid plan is a 30-day pass; when it runs out the account is Free again."""

from dataclasses import asdict, dataclass
from datetime import datetime

from app.models.job import now
from app.models.user import User

PASS_DAYS = 30


@dataclass(frozen=True)
class Plan:
    id: str
    name: str
    price_inr: int  # per 30-day pass; 0 = free
    monthly_videos: int  # videos per rolling 30 days
    max_active: int  # videos being made at once
    rank: int  # higher = better plan

    def public(self) -> dict:
        return {**asdict(self), "days": PASS_DAYS if self.price_inr else None}


PLANS: dict[str, Plan] = {
    p.id: p
    for p in (
        Plan("free", "Free", 0, 5, 1, 0),
        Plan("pro", "Pro", 2_000, 50, 2, 1),
        Plan("max", "Max", 20_000, 500, 3, 2),
    )
}
PAID_PLANS = tuple(p for p in PLANS if PLANS[p].price_inr)


def active_paid_plan(user: User, at: datetime | None = None) -> Plan | None:
    """The paid plan the user has right now, or None (never bought, or expired)."""
    if user.plan == "free" or user.plan_expires_at is None:
        return None
    return PLANS[user.plan] if user.plan_expires_at > (at or now()) else None


def effective_plan(user: User) -> Plan:
    return active_paid_plan(user) or PLANS["free"]
