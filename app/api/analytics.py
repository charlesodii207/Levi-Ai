from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func, cast, Date
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_admin
from app.models.user import User
from app.models.conversation import Conversation
from app.models.message import Message
from app.models.daily_stat import DailyStat
from app.core.subscription_tiers import get_current_price_cents, get_effective_tier
from app.services.analytics_snapshot_service import record_daily_snapshot

router = APIRouter(prefix="/admin/analytics", tags=["Analytics"])


@router.get("/overview")
def get_overview(
    actor=Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = today_start - timedelta(days=7)
    month_start = today_start - timedelta(days=30)

    total_users = db.query(User).count()
    new_users_today = db.query(User).filter(User.created_at >= today_start).count()
    new_users_week = db.query(User).filter(User.created_at >= week_start).count()
    new_users_month = db.query(User).filter(User.created_at >= month_start).count()

    # "Active" here means last_active_at falls in the window. Because this
    # field is overwritten on every request (not logged historically), this
    # gives an accurate count for "active today", but NOT a historical
    # trend — see /activity-log-note below for why a true DAU/WAU/MAU trend
    # chart would need a separate daily log table.
    active_today = db.query(User).filter(User.last_active_at >= today_start).count()
    active_week = db.query(User).filter(User.last_active_at >= week_start).count()
    active_month = db.query(User).filter(User.last_active_at >= month_start).count()

    total_conversations = db.query(Conversation).count()
    total_messages = db.query(Message).count()

    return {
        "total_users": total_users,
        "new_users": {"today": new_users_today, "last_7_days": new_users_week, "last_30_days": new_users_month},
        "active_users": {"today": active_today, "last_7_days": active_week, "last_30_days": active_month},
        "total_conversations": total_conversations,
        "total_messages": total_messages,
        "note": (
            "active_users counts are point-in-time snapshots based on "
            "last_active_at, not a historical trend. A true day-by-day "
            "DAU chart requires a dedicated daily activity log table, "
            "which isn't built yet."
        ),
    }


@router.get("/growth")
def get_growth(
    days: int = 30,
    actor=Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Signups per day for the last N days — genuinely historical, since
    it's derived from User.created_at which never changes after signup."""
    since = datetime.now(timezone.utc) - timedelta(days=days)

    rows = (
        db.query(
            cast(User.created_at, Date).label("day"),
            func.count(User.id).label("signups"),
        )
        .filter(User.created_at >= since)
        .group_by(cast(User.created_at, Date))
        .order_by(cast(User.created_at, Date))
        .all()
    )

    return [{"date": str(r.day), "signups": r.signups} for r in rows]


@router.get("/message-volume")
def get_message_volume(
    days: int = 30,
    actor=Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Messages sent per day for the last N days — a practical proxy for
    overall engagement/activity trend, since it's derived from Message
    rows which are permanent (unlike last_active_at)."""
    since = datetime.now(timezone.utc) - timedelta(days=days)

    rows = (
        db.query(
            cast(Message.created_at, Date).label("day"),
            func.count(Message.id).label("messages"),
        )
        .filter(Message.created_at >= since)
        .group_by(cast(Message.created_at, Date))
        .order_by(cast(Message.created_at, Date))
        .all()
    )

    return [{"date": str(r.day), "messages": r.messages} for r in rows]


@router.get("/models")
def get_model_split(
    actor=Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Split of assistant messages by which model generated them. Only
    covers messages sent after the model/mode tracking columns were added
    — older messages have model=NULL and are excluded here."""
    rows = (
        db.query(Message.model, func.count(Message.id).label("count"))
        .filter(Message.role == "assistant", Message.model.isnot(None))
        .group_by(Message.model)
        .all()
    )
    return [{"model": r.model, "count": r.count} for r in rows]


@router.get("/modes")
def get_mode_adoption(
    actor=Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Split of messages by which mode was active. Only covers messages
    sent after tracking was added. mode=NULL means default/no-mode chat."""
    rows = (
        db.query(
            func.coalesce(Message.mode, "default").label("mode"),
            func.count(Message.id).label("count"),
        )
        .filter(Message.model.isnot(None))  # only rows from after tracking existed
        .group_by(func.coalesce(Message.mode, "default"))
        .all()
    )
    return [{"mode": r.mode, "count": r.count} for r in rows]


@router.get("/history")
def get_daily_history(
    days: int = 30,
    actor=Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """The real historical trend — active users, signups, and messages
    per day, pulled from daily_stats. Unlike /overview's active_users
    (a live snapshot), this is genuine day-by-day history, but only
    covers days since the snapshot job started running."""
    since = (datetime.now(timezone.utc) - timedelta(days=days)).date()

    rows = (
        db.query(DailyStat)
        .filter(DailyStat.date >= since)
        .order_by(DailyStat.date)
        .all()
    )

    return [
        {
            "date": str(r.date),
            "active_users": r.active_users,
            "new_signups": r.new_signups,
            "messages_sent": r.messages_sent,
        }
        for r in rows
    ]


@router.post("/snapshot/run")
def trigger_snapshot(
    for_date: str | None = None,
    actor=Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Manually records a daily_stats row. Defaults to yesterday (UTC) if
    for_date isn't given (format: YYYY-MM-DD). Useful for testing, or as
    a fallback if the automatic scheduler ever misses a day — e.g. if
    the service was asleep at midnight on a free-tier Render plan."""
    parsed_date = None
    if for_date:
        parsed_date = datetime.strptime(for_date, "%Y-%m-%d").date()

    snapshot = record_daily_snapshot(db, for_date=parsed_date)

    return {
        "date": str(snapshot.date),
        "active_users": snapshot.active_users,
        "new_signups": snapshot.new_signups,
        "messages_sent": snapshot.messages_sent,
    }


@router.get("/subscriptions")
def get_subscription_breakdown(
    actor=Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Counts per effective tier plus an estimated MRR (monthly recurring
    revenue) in USD, accounting for each user's individual first-year
    discount status."""
    users = db.query(User).all()

    tier_counts = {"free": 0, "pro": 0, "prime": 0}
    mrr_cents = 0

    for user in users:
        tier = get_effective_tier(user)
        tier_counts[tier] = tier_counts.get(tier, 0) + 1

        if tier in ("pro", "prime"):
            mrr_cents += get_current_price_cents(tier, user.subscription_started_at)

    return {
        "tier_counts": tier_counts,
        "estimated_mrr_usd": round(mrr_cents / 100, 2),
    }
