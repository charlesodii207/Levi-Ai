from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, BigInteger
from sqlalchemy.orm import relationship
from app.database import Base


class KnowledgeBase(Base):
    __tablename__ = "knowledge_base"

    id = Column(Integer, primary_key=True, index=True)

    user_id = Column(
        Integer,
        ForeignKey("users.id"),
        nullable=False
    )

    # File info
    filename = Column(String, nullable=False)
    file_type = Column(String, nullable=False)  # pdf, docx, txt, image, etc.
    file_size = Column(BigInteger, nullable=True)
    storage_path = Column(String, nullable=False)  # path in Supabase storage

    # Extracted content
    content = Column(Text, nullable=True)  # extracted text from file

    created_at = Column(
        DateTime,
        default=datetime.utcnow
    )

    user = relationship(
        "User",
        back_populates="knowledge_base"
    )
