from sqlalchemy import Column, Integer, Text, ForeignKey, DateTime, String, Index
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)

    # index=True — every message load (every chat turn) filters by this.
    # Without it, loading history for a conversation scans ALL messages
    # across every user's every conversation to find the matching rows.
    conversation_id = Column(
        Integer,
        ForeignKey("conversations.id"),
        nullable=False,
        index=True,
    )

    role = Column(Text, nullable=False)  # "user" or "assistant"

    content = Column(Text, nullable=False)

    # Phase 19 — analytics tracking
    model = Column(String, nullable=True)  # "swift" | "nova"
    mode = Column(String, nullable=True)

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now()
    )

    conversation = relationship(
        "Conversation",
        back_populates="messages"
    )

    # Composite index — message history queries filter by conversation_id
    # AND sort by created_at ascending in the same query.
    __table_args__ = (
        Index("ix_messages_conversation_id_created_at", "conversation_id", "created_at"),
    )
