from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.database import Base


class SuspensionAppeal(Base):
    __tablename__ = "suspension_appeals"

    id = Column(Integer, primary_key=True, index=True)

    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    email = Column(String, nullable=False)  # snapshot at submission time, for convenience
    message = Column(Text, nullable=False)

    status = Column(String, nullable=False, default="pending")  # "pending" | "approved" | "rejected"

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    resolved_at = Column(DateTime, nullable=True)
    resolved_by = Column(Integer, ForeignKey("admins.id"), nullable=True)

    user = relationship("User")
    resolver = relationship("Admin")
