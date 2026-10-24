"""Memberships: the plans, buying a pass (Stripe Checkout), Stripe's webhook, and payment history."""

import logging
from datetime import timedelta
from typing import Literal

import stripe
from fastapi import APIRouter, HTTPException, Query, Request, status
from pydantic import BaseModel
from pymongo.errors import DuplicateKeyError

from app.auth import CurrentUser
from app.billing import service
from app.billing.gateway import BillingNotConfigured
from app.billing.plans import PLANS, effective_plan
from app.config import settings
from app.models.billing import Payment, StripeEvent
from app.models.job import now

router = APIRouter(prefix="/api/billing", tags=["billing"])
log = logging.getLogger(__name__)


class CheckoutRequest(BaseModel):
    plan: Literal["pro", "max"]


def _http(exc: Exception) -> HTTPException:
    if isinstance(exc, service.BillingError):
        return HTTPException(exc.status, detail=exc.detail)
    if isinstance(exc, BillingNotConfigured):
        return HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))
    log.exception("Stripe request failed")
    return HTTPException(
        status.HTTP_502_BAD_GATEWAY,
        detail="Couldn't reach the payment provider. Please try again in a minute.",
    )


def payment_row(p: Payment) -> dict:
    return {
        "id": str(p.id),
        "plan": p.plan,
        "plan_name": PLANS[p.plan].name,
        "amount": p.amount / 100,  # rupees
        "currency": p.currency,
        "status": p.status,
        "card_brand": p.card_brand,
        "card_last4": p.card_last4,
        "receipt_url": p.receipt_url,
        "period_start": p.period_start,
        "period_end": p.period_end,
        "created_at": p.created_at,
        "paid_at": p.paid_at,
    }


@router.get("/plans")
async def plans() -> list[dict]:
    """Public: the plans and their prices."""
    return [p.public() for p in PLANS.values()]


@router.post("/checkout")
async def checkout(body: CheckoutRequest, user: CurrentUser) -> dict:
    """Start buying a 30-day pass; the browser then goes to Stripe's checkout page (`url`)."""
    try:
        return {"url": await service.start_checkout(user, body.plan)}
    except (service.BillingError, BillingNotConfigured, stripe.StripeError) as exc:
        raise _http(exc) from exc


@router.get("/confirm")
async def confirm(user: CurrentUser, session_id: str = Query(max_length=200)) -> dict:
    """Back from Stripe: apply the pass if it's paid (the webhook may not have arrived yet)."""
    try:
        payment = await service.fulfill(session_id, user)
    except (service.BillingError, BillingNotConfigured, stripe.StripeError) as exc:
        raise _http(exc) from exc
    refreshed = await type(user).get(user.id)
    plan = effective_plan(refreshed)
    return {
        "payment": payment_row(payment),
        "plan": plan.id,
        "plan_name": plan.name,
        "plan_expires_at": refreshed.plan_expires_at if plan.price_inr else None,
    }


@router.get("/payments")
async def payments(user: CurrentUser) -> list[dict]:
    """The user's payments, newest first (abandoned checkouts are left out after an hour)."""
    recent = now() - timedelta(hours=1)
    rows = (
        await Payment.find(
            {
                "user_id": user.id,
                "$or": [
                    {"status": {"$in": ["paid", "needs_review", "failed"]}},
                    {"status": "pending", "created_at": {"$gte": recent}},
                ],
            }
        )
        .sort("-created_at")
        .to_list()
    )
    return [payment_row(p) for p in rows]


@router.post("/webhook")
async def webhook(request: Request) -> dict:
    """Stripe calls this. Each event is verified by its signature and handled once."""
    if not settings.stripe_webhook_secret:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, detail="webhook secret not set"
        )
    payload = await request.body()
    try:
        event = stripe.Webhook.construct_event(
            payload,
            request.headers.get("stripe-signature"),
            settings.stripe_webhook_secret,
        ).to_dict()
    except (ValueError, stripe.SignatureVerificationError) as exc:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail="invalid signature"
        ) from exc

    try:
        await StripeEvent(id=event["id"], type=event["type"]).insert()
    except DuplicateKeyError:
        return {"received": True, "duplicate": True}

    kind, session_id = event["type"], event["data"]["object"].get("id", "")
    try:
        if kind in (
            "checkout.session.completed",
            "checkout.session.async_payment_succeeded",
        ):
            await service.fulfill(session_id)
        elif kind == "checkout.session.expired":
            await service.mark_unpaid(session_id, "expired")
        elif kind == "checkout.session.async_payment_failed":
            await service.mark_unpaid(session_id, "failed")
    except Exception:
        # Forget the event so Stripe's automatic retry is processed again.
        await StripeEvent.find_one(StripeEvent.id == event["id"]).delete()
        log.exception("Handling Stripe event %s (%s) failed", event["id"], kind)
        raise
    return {"received": True}
