"""Buying a 30-day pass: start a Stripe Checkout Session, then apply the pass once it's paid.

`fulfill` is the only place a pass is granted. The webhook and the "back from Stripe" page both
call it; it asks Stripe for the session itself and claims the payment atomically, so a pass is
applied exactly once however many times (and from wherever) it is called.
"""

import logging
from datetime import datetime, timedelta

from app.billing.gateway import get_gateway
from app.billing.plans import PASS_DAYS, PLANS, active_paid_plan
from app.config import settings
from app.models.billing import Payment
from app.models.job import now
from app.models.user import User

log = logging.getLogger(__name__)


class BillingError(Exception):
    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status, self.detail = status, detail


def _date(at: datetime) -> str:
    return at.strftime("%-d %b %Y")


async def start_checkout(user: User, plan_id: str) -> str:
    """Create a Checkout Session for a pass and record it as pending; returns Stripe's page URL."""
    plan = PLANS[plan_id]
    current = active_paid_plan(user)
    if current and current.rank > plan.rank:
        raise BillingError(
            409,
            f"You're on {current.name} until {_date(user.plan_expires_at)}. "
            f"A {plan.name} pass can be bought after that.",
        )
    base = settings.app_base_url.rstrip("/")
    session = await get_gateway().create_checkout(
        mode="payment",
        line_items=[
            {
                "price_data": {
                    "currency": "inr",
                    "unit_amount": plan.price_inr * 100,  # paise
                    "product_data": {
                        "name": f"Mindsketch.ai {plan.name}: {PASS_DAYS}-day pass",
                        "description": f"{plan.monthly_videos} videos per {PASS_DAYS} days, "
                        f"{plan.max_active} at once",
                    },
                },
                "quantity": 1,
            }
        ],
        customer_email=user.email,
        client_reference_id=str(user.id),
        metadata={"user_id": str(user.id), "plan": plan.id},
        success_url=f"{base}/profile?checkout=success&session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=f"{base}/profile?checkout=cancelled",
    )
    await Payment(
        user_id=user.id,
        plan=plan.id,
        amount=plan.price_inr * 100,
        stripe_session_id=session["id"],
    ).insert()
    return session["url"]


async def _extend_membership(user_id, plan_id: str) -> tuple[datetime, datetime] | None:
    """Apply a pass to the account; returns the period it covers, or None if it can't apply.

    Same plan still active: 30 more days from its current end. Free, expired, or a higher plan:
    30 days from now. A lower plan while a higher one is active: None (the payment needs review).
    The update only succeeds if the plan didn't change meanwhile, so two passes paid at the same
    moment both count.
    """
    collection = User.get_pymongo_collection()
    for _ in range(5):
        user = await User.get(user_id)
        if user is None:
            return None
        plan, current = PLANS[plan_id], active_paid_plan(user)
        if current and current.rank > plan.rank:
            return None
        start = user.plan_expires_at if current and current.id == plan.id else now()
        end = start + timedelta(days=PASS_DAYS)
        # Accounts made before memberships have no `plan` field yet (None matches a missing one).
        plan_now = {"$in": ["free", None]} if user.plan == "free" else user.plan
        result = await collection.update_one(
            {"_id": user.id, "plan": plan_now, "plan_expires_at": user.plan_expires_at},
            {"$set": {"plan": plan.id, "plan_expires_at": end}},
        )
        if result.modified_count == 1:
            return start, end
    raise RuntimeError(f"membership of user {user_id} kept changing; not applied")


async def fulfill(session_id: str, user: User | None = None) -> Payment | None:
    """Grant the pass a Checkout Session paid for, once. Returns its payment record.

    `user`, when given, must own the session (404 otherwise). An unknown session gives None.
    """
    payment = await Payment.find_one(Payment.stripe_session_id == session_id)
    if payment is None or (user is not None and payment.user_id != user.id):
        if user is not None:
            raise BillingError(404, "No such payment")
        log.warning("Stripe session %s is not one of ours", session_id)
        return None
    if payment.status in ("paid", "needs_review"):
        return payment

    session = await get_gateway().retrieve_session(session_id)
    if session["payment_status"] not in ("paid", "no_payment_required"):
        return payment  # not paid (yet): an async method may still succeed
    wrong = (
        session["amount_total"] != payment.amount
        or session["metadata"].get("plan") != payment.plan
    )

    # Claim it: only one caller moves it out of pending/failed.
    paid_at = now()
    claimed = await Payment.get_pymongo_collection().find_one_and_update(
        {"_id": payment.id, "status": {"$in": ["pending", "failed", "expired"]}},
        {
            "$set": {
                "status": "paid",
                "paid_at": paid_at,
                "payment_intent": session["payment_intent"],
                "card_brand": session["card_brand"],
                "card_last4": session["card_last4"],
                "receipt_url": session["receipt_url"],
            }
        },
    )
    if claimed is None:
        return await Payment.get(payment.id)  # someone else just fulfilled it

    period = None if wrong else await _extend_membership(payment.user_id, payment.plan)
    if period is None:
        note = (
            "amount or plan doesn't match what was charged"
            if wrong
            else "a higher plan was active when this was paid; refund it from the Stripe Dashboard"
        )
        update = {"status": "needs_review", "note": note}
        log.error("Payment %s needs review: %s", payment.id, note)
    else:
        update = {"period_start": period[0], "period_end": period[1]}
        log.info(
            "User %s: %s until %s (session %s)",
            payment.user_id,
            payment.plan,
            period[1],
            session_id,
        )
    await Payment.find_one(Payment.id == payment.id).update({"$set": update})
    return await Payment.get(payment.id)


async def mark_unpaid(session_id: str, status: str) -> None:
    """A session that expired or whose payment failed: record it (only while still pending)."""
    await Payment.find_one(
        {"stripe_session_id": session_id, "status": "pending"}
    ).update({"$set": {"status": status}})
