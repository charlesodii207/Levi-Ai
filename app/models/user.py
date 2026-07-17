from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Integer, String
from sqlalchemy.orm import relationship

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, nullable=False)
    email = Column(String, unique=True, nullable=False)
    hashed_password = Column(String, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow)

    is_active = Column(Boolean, default=True)
    is_verified = Column(Boolean, default=False)

    otp_code = Column(String, nullable=True)
    otp_expiry = Column(DateTime, nullable=True)

    # Set on login only
    last_login_at = Column(DateTime, nullable=True)
    last_login_ip = Column(String, nullable=True)

    # NEW — updated on every authenticated request (not just login).
    # This is what powers real "online now" status, since a user can
    # be logged in for days without actually being active right now.
    last_active_at = Column(DateTime, nullable=True)

    # Relationships
    conversations = relationship(
        "Conversation",
        back_populates="user",
        cascade="all, delete-orphan"
    )

    memories = relationship(
        "Memory",
        back_populates="user",
        cascade="all, delete-orphan"
    )

    knowledge_base = relationship(
        "KnowledgeBase",
        back_populates="user",
        cascade="all, delete-orphan"
    )
