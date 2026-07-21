from sqlalchemy import Column, Integer, Text, ForeignKey, DateTime, String
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)

    conversation_id = Column(
        Integer,
        ForeignKey("conversations.id"),
        nullable=False
    )

    role = Column(Text, nullable=False)  # "user" or "assistant"

    content = Column(Text, nullable=False)

    # ------------------------------------------------------------------
    # Phase 19 — analytics tracking
    # ------------------------------------------------------------------
    # Which AI model generated this message. Only set on assistant
    # messages going forward — historical rows will be NULL.
    model = Column(String, nullable=True)  # "swift" | "nova"

    # Which mode (Coding, Crypto, Business, etc.) was active when this
    # message was sent. NULL means default/no mode. Also only populated
    # going forward.
    mode = Column(String, nullable=True)

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now()
    )

    conversation = relationship(
        "Conversation",
        back_populates="messages"
    )
