from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from app.database import Base


class Admin(Base):
    __tablename__ = "admins"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, nullable=False, index=True)
    hashed_password = Column(String, nullable=False)

    # One of: "owner", "super_admin", "admin", "moderator"
    # See app/core/tiers.py for the authority ranking these map to.
    tier = Column(String, nullable=False, default="moderator")

    # Only meaningful when tier == "admin" (Tier 3 — Administrator).
    # One of: "technical", "operations", "finance", "analytics",
    # "support", "communications". Null for every other tier —
    # Tier 2 is always displayed as "Executive" (fixed, not stored
    # as a selectable role), and Tier 1/4 have no departmental role.
    platform_role = Column(String, nullable=True)

    status = Column(String, nullable=False, default="active")  # "active" or "blocked"

    # Forced on every account created by another admin. Cleared once
    # the admin changes their own password for the first time.
    must_change_password = Column(Boolean, default=True)

    # Who created this admin account (null for the bootstrapped owner)
    created_by = Column(Integer, ForeignKey("admins.id"), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Set on login only
    last_login_at = Column(DateTime, nullable=True)
    last_login_ip = Column(String, nullable=True)

    # Updated on every authenticated request — powers "online now" status
    last_active_at = Column(DateTime, nullable=True)

    action_logs = relationship(
        "AdminActionLog",
        back_populates="admin",
        cascade="all, delete-orphan",
    )
