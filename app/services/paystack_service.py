"""
paystack_service.py

Thin wrapper around Paystack's REST API: starting a payment, verifying a
transaction, and checking webhook signatures so we know events genuinely
came from Paystack and not a spoofed request.
"""

import hashlib
import hmac
import os

import requests

PAYSTACK_SECRET_KEY = os.getenv("PAYSTACK_SECRET_KEY")
PAYSTACK_BASE_URL = "https://api.paystack.co"


def _headers() -> dict:
    return {"Authorization": f"Bearer {PAYSTACK_SECRET_KEY}"}


def initialize_transaction(
    email: str,
    amount: int,
    currency: str = "NGN",
    metadata: dict | None = None,
) -> dict:
    """Starts a payment. `amount` is in the smallest currency unit (kobo
    for NGN, cents for USD). Returns Paystack's response, which includes
    `data.authorization_url` — redirect the user there to pay."""
    payload = {
        "email": email,
        "amount": amount,
        "currency": currency,
    }
    if metadata:
        payload["metadata"] = metadata

    resp = requests.post(
        f"{PAYSTACK_BASE_URL}/transaction/initialize",
        json=payload,
        headers=_headers(),
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def verify_transaction(reference: str) -> dict:
    """Confirms a transaction actually succeeded, server-to-server —
    never trust a client-reported 'payment succeeded' on its own."""
    resp = requests.get(
        f"{PAYSTACK_BASE_URL}/transaction/verify/{reference}",
        headers=_headers(),
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def verify_webhook_signature(raw_body: bytes, signature: str | None) -> bool:
    """Paystack signs webhook payloads with HMAC-SHA512 using your secret
    key. Recompute it here and compare — if it doesn't match, the request
    didn't genuinely come from Paystack."""
    if not signature or not PAYSTACK_SECRET_KEY:
        return False

    expected = hmac.new(
        PAYSTACK_SECRET_KEY.encode("utf-8"),
        raw_body,
        hashlib.sha512,
    ).hexdigest()

    return hmac.compare_digest(expected, signature)
