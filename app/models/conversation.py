from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Index
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(Integer, primary_key=True, index=True)

    # index=True — every conversation list/load query filters by user_id.
    # Without this, each of those queries scans the whole table.
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    title = Column(String, default="New Chat")

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now()
    )

    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    user = relationship(
        "User",
        back_populates="conversations"
    )

    messages = relationship(
        "Message",
        back_populates="conversation",
        cascade="all, delete-orphan"
    )

    # Composite index — list_conversations filters by user_id AND sorts
    # by updated_at descending in the same query. A composite index lets
    # Postgres satisfy both parts in one pass instead of filtering, then
    # sorting the results separately.
    __table_args__ = (
        Index("ix_conversations_user_id_updated_at", "user_id", "updated_at"),
    )
