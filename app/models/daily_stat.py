from sqlalchemy import Column, Integer, Date, DateTime
from sqlalchemy.sql import func

from app.database import Base


class DailyStat(Base):
    """One row per calendar day (UTC), summarizing that day's activity.
    Written once daily by the snapshot job (or manually via
    /admin/analytics/snapshot/run) — this is what makes real historical
    trend charts (active users over time, etc.) possible, since fields
    like User.last_active_at only ever hold the MOST RECENT value and
    can't answer "how many were active on July 15th" after the fact."""

    __tablename__ = "daily_stats"

    id = Column(Integer, primary_key=True, index=True)
    date = Column(Date, unique=True, nullable=False, index=True)

    active_users = Column(Integer, nullable=False, default=0)
    new_signups = Column(Integer, nullable=False, default=0)
    messages_sent = Column(Integer, nullable=False, default=0)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
