"""
currency_service.py

Fetches a live USD -> NGN exchange rate so Paystack checkout can charge
the Naira equivalent of a USD-denominated price shown on the landing
page. Uses a free, keyless exchange rate API and caches the result in
memory for an hour — checkout doesn't need a rate that's fresh to the
second, and this avoids hammering the external API on every subscribe
click.
"""

import logging
import time

import requests

logger = logging.getLogger("currency_service")

EXCHANGE_RATE_URL = "https://open.er-api.com/v6/latest/USD"
CACHE_TTL_SECONDS = 60 * 60  # 1 hour

# Used only if the live rate fetch fails AND the cache is empty/expired.
# Update this occasionally so the fallback doesn't drift too far from
# reality — it's a safety net, not the primary source of truth.
FALLBACK_USD_TO_NGN = 1600.0

_cache: dict = {"rate": None, "fetched_at": 0.0}


def get_usd_to_ngn_rate() -> float:
    now = time.time()

    if _cache["rate"] is not None and (now - _cache["fetched_at"]) < CACHE_TTL_SECONDS:
        return _cache["rate"]

    try:
        resp = requests.get(EXCHANGE_RATE_URL, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        rate = float(data["rates"]["NGN"])

        _cache["rate"] = rate
        _cache["fetched_at"] = now
        return rate

    except Exception:
        logger.exception("Failed to fetch live USD->NGN rate, using fallback")
        # Serve a stale cached rate over the hardcoded fallback if we have one
        if _cache["rate"] is not None:
            return _cache["rate"]
        return FALLBACK_USD_TO_NGN


def usd_cents_to_ngn_kobo(usd_cents: int) -> int:
    """Converts a USD amount (in cents) to the NGN kobo equivalent,
    using the current live exchange rate. Paystack expects amounts in
    the smallest currency unit (kobo for NGN, same as cents for USD)."""
    rate = get_usd_to_ngn_rate()
    usd_amount = usd_cents / 100
    ngn_amount = usd_amount * rate
    return round(ngn_amount * 100)  # convert to kobo
