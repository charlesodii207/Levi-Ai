"""
analytics_snapshot_service.py

Computes and saves one day's worth of analytics numbers into the
daily_stats table. Meant to run once daily, shortly after midnight UTC,
capturing the day that just ended — but safe to re-run for the same
date (it upserts rather than duplicating), so it also works as a manual
backfill/testing tool via /admin/analytics/snapshot/run.
"""

import logging
from datetime import date as date_cls
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models.user import User
from app.models.message import Message
from app.models.daily_stat import DailyStat

logger = logging.getLogger("analytics_snapshot")


def record_daily_snapshot(db: Session, for_date: date_cls | None = None) -> DailyStat:
    if for_date is None:
        # Default: yesterday, UTC — this job normally runs just after
        # midnight to summarize the day that just ended.
        for_date = (datetime.now(timezone.utc) - timedelta(days=1)).date()

    day_start = datetime(for_date.year, for_date.month, for_date.day, tzinfo=timezone.utc)
    day_end = day_start + timedelta(days=1)

    active_users = (
        db.query(User)
        .filter(User.last_active_at >= day_start, User.last_active_at < day_end)
        .count()
    )

    new_signups = (
        db.query(User)
        .filter(User.created_at >= day_start, User.created_at < day_end)
        .count()
    )

    messages_sent = (
        db.query(Message)
        .filter(Message.created_at >= day_start, Message.created_at < day_end)
        .count()
    )

    existing = db.query(DailyStat).filter(DailyStat.date == for_date).first()
    if existing:
        existing.active_users = active_users
        existing.new_signups = new_signups
        existing.messages_sent = messages_sent
        db.commit()
        db.refresh(existing)
        return existing

    snapshot = DailyStat(
        date=for_date,
        active_users=active_users,
        new_signups=new_signups,
        messages_sent=messages_sent,
    )
    db.add(snapshot)
    db.commit()
    db.refresh(snapshot)
    return snapshot


def run_scheduled_snapshot() -> None:
    """Entry point for the scheduler — opens its own DB session since it
    runs outside a normal request/response cycle."""
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        snapshot = record_daily_snapshot(db)
        logger.info(
            "Recorded daily snapshot for %s: active=%d signups=%d messages=%d",
            snapshot.date, snapshot.active_users, snapshot.new_signups, snapshot.messages_sent,
        )
    except Exception:
        logger.exception("Daily analytics snapshot job failed")
    finally:
        db.close()
