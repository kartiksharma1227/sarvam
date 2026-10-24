"""The two Stripe calls Mindsketch makes, behind a small interface so tests can use a fake.

Sessions come back as plain dicts with the fields the app uses (see `session_fields`).
"""

import os
import ssl
from typing import Protocol

import httpx
import stripe

from app.config import settings

# Tags our Checkout Sessions in the Stripe Dashboard (a label plus 8 random letters).
INTEGRATION_ID = "mindsketch_pass_qhvtrkwm"


class PaymentGateway(Protocol):
    async def create_checkout(self, **params) -> dict: ...
    async def retrieve_session(self, session_id: str) -> dict: ...


class BillingNotConfigured(RuntimeError):
    pass


def session_fields(session: dict) -> dict:
    """The fields of a Checkout Session (as a plain dict) the app needs.

    With `payment_intent.latest_charge` expanded, it also gives the card and the receipt link.
    """
    intent = session.get("payment_intent")
    charge = (intent or {}).get("latest_charge") if isinstance(intent, dict) else None
    charge = charge if isinstance(charge, dict) else {}
    card = (charge.get("payment_method_details") or {}).get("card") or {}
    return {
        "id": session["id"],
        "url": session.get("url"),
        "status": session.get("status"),
        "payment_status": session.get("payment_status"),
        "amount_total": session.get("amount_total"),
        "currency": session.get("currency"),
        "client_reference_id": session.get("client_reference_id"),
        "metadata": dict(session.get("metadata") or {}),
        "payment_intent": intent.get("id") if isinstance(intent, dict) else intent,
        "card_brand": card.get("brand"),
        "card_last4": card.get("last4"),
        "receipt_url": charge.get("receipt_url"),
    }


class StripeGateway:
    def __init__(self, api_key: str, proxy: str | None = None):
        http_client = stripe.HTTPXClient()
        if proxy:
            # The SDK's own `proxy` option passes an argument httpx 0.28 no longer accepts,
            # so give it an httpx client that already goes through the proxy.
            http_client._client_async = httpx.AsyncClient(
                proxy=proxy,
                verify=ssl.create_default_context(cafile=stripe.ca_bundle_path),
            )
        self.client = stripe.StripeClient(api_key, http_client=http_client)

    async def create_checkout(self, **params) -> dict:
        session = await self.client.v1.checkout.sessions.create_async(
            {**params, "integration_identifier": INTEGRATION_ID}
        )
        return session_fields(session.to_dict())

    async def retrieve_session(self, session_id: str) -> dict:
        session = await self.client.v1.checkout.sessions.retrieve_async(
            session_id, {"expand": ["payment_intent.latest_charge"]}
        )
        return session_fields(session.to_dict())


_gateway: PaymentGateway | None = None


def get_gateway() -> PaymentGateway:
    """The Stripe gateway (tests replace it with `set_gateway`)."""
    global _gateway
    if _gateway is None:
        if not settings.stripe_secret_key:
            raise BillingNotConfigured(
                "Payments aren't set up yet (STRIPE_SECRET_KEY is empty in backend/.env)."
            )
        proxy = (
            settings.stripe_proxy
            or os.environ.get("HTTPS_PROXY")
            or os.environ.get("https_proxy")
        )
        _gateway = StripeGateway(settings.stripe_secret_key, proxy)
    return _gateway


def set_gateway(gateway: PaymentGateway | None) -> None:
    global _gateway
    _gateway = gateway
