"""Membership payments (collection `payments`) and Stripe events already handled (`stripe_events`)."""

from datetime import datetime
from typing import ClassVar, Literal

from beanie import Document, PydanticObjectId
from pydantic import Field
from pymongo import ASCENDING, DESCENDING, IndexModel

from app.models.job import now

PaymentStatus = Literal["pending", "paid", "expired", "failed", "needs_review"]


class Payment(Document):
    """One Stripe Checkout Session for a 30-day pass. Amounts are in paise (₹1 = 100)."""

    user_id: PydanticObjectId
    plan: str
    amount: int
    currency: str = "inr"
    status: PaymentStatus = "pending"
    stripe_session_id: str
    payment_intent: str | None = None
    card_brand: str | None = None
    card_last4: str | None = None
    receipt_url: str | None = None
    period_start: datetime | None = None  # the membership this payment bought
    period_end: datetime | None = None
    note: str | None = None  # e.g. why it needs review
    created_at: datetime = Field(default_factory=now)
    paid_at: datetime | None = None

    class Settings:
        name = "payments"
        indexes: ClassVar = [
            IndexModel([("stripe_session_id", ASCENDING)], unique=True),
            IndexModel([("user_id", ASCENDING), ("created_at", DESCENDING)]),
        ]


class StripeEvent(Document):
    """A webhook event that was processed, so a redelivery is skipped. `id` is Stripe's event id."""

    id: str  # type: ignore[assignment]
    type: str
    received_at: datetime = Field(default_factory=now)

    class Settings:
        name = "stripe_events"
