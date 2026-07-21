"""
subscription_tiers.py

Defines what each subscription tier gets, and enforces daily activity
limits + model access. Called from the chat endpoint before generating
any AI response.

Pricing note: amounts are in USD cents. Confirm your Paystack account
actually supports USD transactions before going live — if not, these
need converting to NGN (kobo) instead.
"""

from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.user import User

DISCOUNT_PERIOD_DAYS = 365  # first-year discount window

# Daily activity limit per tier. None = unlimited.
TIER_LIMITS = {
    "free": {"daily_limit": 25, "allowed_models": {"swift"}},
    "pro": {"daily_limit": 100, "allowed_models": {"swift", "nova"}},
    "prime": {"daily_limit": None, "allowed_models": {"swift", "nova"}},
}

# USD cents. "full" = price after the first-year discount ends.
# "discounted" = price for the first 12 months of a NEW subscription.
PLAN_PRICING = {
    "pro": {"full": 2000, "discounted": 1200, "discount_percent": 40},
    "prime": {"full": 10000, "discounted": 4500, "discount_percent": 55},
}


def get_current_price_cents(tier: str, subscription_started_at: datetime | None) -> int:
    """Price for this tier right now, accounting for the first-year discount."""
    pricing = PLAN_PRICING[tier]
    if subscription_started_at is None:
        return pricing["discounted"]

    started = subscription_started_at
    if started.tzinfo is None:
        started = started.replace(tzinfo=timezone.utc)

    age_days = (datetime.now(timezone.utc) - started).days
    return pricing["discounted"] if age_days < DISCOUNT_PERIOD_DAYS else pricing["full"]


def get_effective_tier(user: User) -> str:
    """The tier that actually applies right now — falls back to 'free' if
    a paid subscription has expired without renewal, even if the stored
    subscription_tier field still says 'pro'/'prime'."""
    tier = user.subscription_tier or "free"

    if tier in ("pro", "prime"):
        if user.subscription_status != "active":
            return "free"
        if user.subscription_expires_at is None:
            return "free"

        expires = user.subscription_expires_at
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)

        if expires < datetime.now(timezone.utc):
            return "free"

    return tier


def check_and_consume_activity(db: Session, user: User, model: str) -> None:
    """Call this before letting a chat message through. Raises HTTPException
    if the model isn't allowed on the user's tier, or if they've hit their
    daily limit. Otherwise increments their usage counter."""
    tier = get_effective_tier(user)
    limits = TIER_LIMITS[tier]

    if model not in limits["allowed_models"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                f"The '{model}' model isn't available on your current plan "
                f"({tier}). Upgrade to unlock it."
            ),
        )

    today = datetime.now(timezone.utc).date()
    if user.daily_activity_date != today:
        user.daily_activity_count = 0
        user.daily_activity_date = today

    daily_limit = limits["daily_limit"]
    if daily_limit is not None and user.daily_activity_count >= daily_limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                f"You've reached your daily limit of {daily_limit} activities "
                f"on the {tier} plan. Upgrade for more, or try again tomorrow."
            ),
        )

    user.daily_activity_count += 1
    db.commit()
