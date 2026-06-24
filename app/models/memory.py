from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.orm import relationship

from app.database import Base


class Memory(Base):
    __tablename__ = "memories"

    id = Column(Integer, primary_key=True, index=True)

    user_id = Column(
        Integer,
        ForeignKey("users.id"),
        nullable=False
    )

    key = Column(
        String,
        nullable=False
    )

    value = Column(
        String,
        nullable=False
    )

    user = relationship(
        "User",
        back_populates="memories"
    )