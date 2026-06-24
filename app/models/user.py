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

    # Relationship with conversations
    conversations = relationship(
        "Conversation",
        back_populates="user",
        cascade="all, delete-orphan"
    )

    # Relationship with memories
    memories = relationship(
        "Memory",
        back_populates="user",
        cascade="all, delete-orphan"
    )