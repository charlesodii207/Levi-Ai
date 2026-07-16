from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.database import Base


class AdminActionLog(Base):
    __tablename__ = "admin_action_logs"

    id = Column(Integer, primary_key=True, index=True)
    admin_id = Column(Integer, ForeignKey("admins.id"), nullable=False)

    action = Column(String, nullable=False)       # e.g. "blocked_admin", "suspended_user"
    target_type = Column(String, nullable=True)   # e.g. "user", "admin"
    target_id = Column(Integer, nullable=True)
    details = Column(Text, nullable=True)

    ip_address = Column(String, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    admin = relationship("Admin", back_populates="action_logs")
