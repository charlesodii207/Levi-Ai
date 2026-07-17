from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from app.database import Base


class Admin(Base):
    __tablename__ = "admins"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, nullable=False, index=True)
    hashed_password = Column(String, nullable=False)

    role = Column(String, nullable=False, default="junior")    # "senior" or "junior"
    status = Column(String, nullable=False, default="active")  # "active" or "blocked"

    # Forced on every account created by a senior admin. Cleared once
    # the admin changes their own password for the first time.
    must_change_password = Column(Boolean, default=True)

    # Who created this admin account (null for the bootstrapped senior admin)
    created_by = Column(Integer, ForeignKey("admins.id"), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Set on login only
    last_login_at = Column(DateTime, nullable=True)
    last_login_ip = Column(String, nullable=True)

    # NEW — updated on every authenticated admin request, powers
    # "online now" status the same way it does for regular users.
    last_active_at = Column(DateTime, nullable=True)

    action_logs = relationship(
        "AdminActionLog",
        back_populates="admin",
        cascade="all, delete-orphan",
    )
