from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.schemas.billing import (
    SubscribeRequest,
    SubscribeResponse,
    BillingStatusOut,
    PlanOut,
)
from app.services.paystack_service import (
    initialize_transaction,
    verify_transaction,
    verify_webhook_signature,
)
from app.services.currency_service import usd_cents_to_ngn_kobo, get_usd_to_ngn_rate
from app.core.subscription_tiers import (
    TIER_LIMITS,
    PLAN_PRICING,
    get_current_price_cents,
    get_effective_tier,
)

router = APIRouter(prefix="/billing", tags=["Billing"])

SUBSCRIPTION_PERIOD_DAYS = 30


@router.get("/plans", response_model=list[PlanOut])
def get_plans(current_user: User = Depends(get_current_user)):
    """Prices shown here are in USD — the landing page displays these
    directly. Actual Paystack checkout converts to NGN at the live rate
    when /subscribe is called."""
    plans = [
        PlanOut(
            name="free",
            price_usd=0,
            daily_limit=TIER_LIMITS["free"]["daily_limit"],
            models=list(TIER_LIMITS["free"]["allowed_models"]),
        )
    ]

    for tier in ("pro", "prime"):
        price_cents = get_current_price_cents(tier, current_user.subscription_started_at)
        pricing = PLAN_PRICING[tier]
        extras = []
        if tier == "prime":
            extras = ["API access", "Shared team workspace"]

        plans.append(
            PlanOut(
                name=tier,
                price_usd=price_cents / 100,
                original_price_usd=pricing["full"] / 100,
                discount_percent=pricing["discount_percent"],
                daily_limit=TIER_LIMITS[tier]["daily_limit"],
                models=list(TIER_LIMITS[tier]["allowed_models"]),
                extras=extras,
            )
        )

    return plans


@router.post("/subscribe", response_model=SubscribeResponse)
def subscribe(
    body: SubscribeRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if body.tier not in ("pro", "prime"):
        raise HTTPException(status_code=400, detail="Invalid tier — must be 'pro' or 'prime'.")

    usd_price_cents = get_current_price_cents(body.tier, current_user.subscription_started_at)
    ngn_kobo = usd_cents_to_ngn_kobo(usd_price_cents)
    rate_used = get_usd_to_ngn_rate()

    reference = f"levi_{current_user.id}_{int(datetime.now(timezone.utc).timestamp())}"

    result = initialize_transaction(
        email=current_user.email,
        amount=ngn_kobo,
        currency="NGN",
        metadata={
            "user_id": current_user.id,
            "tier": body.tier,
            "usd_price_cents": usd_price_cents,
            "usd_to_ngn_rate_used": rate_used,
            "reference": reference,
        },
    )

    if not result.get("status"):
        raise HTTPException(status_code=502, detail="Failed to start payment with Paystack.")

    return {
        "authorization_url": result["data"]["authorization_url"],
        "reference": result["data"]["reference"],
    }


@router.post("/webhook")
async def paystack_webhook(request: Request, db: Session = Depends(get_db)):
    raw_body = await request.body()
    signature = request.headers.get("x-paystack-signature")

    if not verify_webhook_signature(raw_body, signature):
        raise HTTPException(status_code=400, detail="Invalid webhook signature.")

    payload = await request.json()
    event = payload.get("event")

    if event == "charge.success":
        data = payload.get("data", {})
        metadata = data.get("metadata", {})
        user_id = metadata.get("user_id")
        tier = metadata.get("tier")

        if user_id and tier:
            # Re-verify server-to-server rather than trusting the webhook
            # payload alone — belt and suspenders against spoofed events.
            reference = data.get("reference")
            verification = verify_transaction(reference)
            if not verification.get("data", {}).get("status") == "success":
                return {"status": "ignored", "reason": "verification failed"}

            user = db.query(User).filter(User.id == user_id).first()
            if user:
                now = datetime.now(timezone.utc)
                if user.subscription_started_at is None:
                    user.subscription_started_at = now

                user.subscription_tier = tier
                user.subscription_status = "active"
                user.subscription_expires_at = now + timedelta(days=SUBSCRIPTION_PERIOD_DAYS)
                user.paystack_customer_code = data.get("customer", {}).get("customer_code")

                authorization = data.get("authorization", {})
                if authorization.get("reusable"):
                    user.paystack_authorization_code = authorization.get("authorization_code")

                db.commit()

    return {"status": "ok"}


@router.get("/status", response_model=BillingStatusOut)
def billing_status(current_user: User = Depends(get_current_user)):
    tier = get_effective_tier(current_user)
    limits = TIER_LIMITS[tier]

    return {
        "tier": tier,
        "status": current_user.subscription_status,
        "expires_at": str(current_user.subscription_expires_at) if current_user.subscription_expires_at else None,
        "daily_activity_count": current_user.daily_activity_count,
        "daily_limit": limits["daily_limit"],
    }
