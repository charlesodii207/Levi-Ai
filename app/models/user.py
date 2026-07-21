from datetime import datetime

from sqlalchemy import Boolean, Column, Date, DateTime, Integer, String
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

    # Updated on every authenticated request (not just login).
    # This is what powers real "online now" status.
    last_active_at = Column(DateTime, nullable=True)

    # ------------------------------------------------------------------
    # Phase 16 — user settings
    # ------------------------------------------------------------------
    bio = Column(String, nullable=True)
    avatar_url = Column(String, nullable=True)

    # "swift" (Groq/Llama) or "nova" (Gemini) — matches ChatRequest.model
    default_model = Column(String, default="swift", nullable=False)

    theme = Column(String, default="dark", nullable=False)  # "light" | "dark"
    email_notifications = Column(Boolean, default=True, nullable=False)

    # Holds a new email address until the OTP sent to it is confirmed.
    pending_email = Column(String, nullable=True)

    # ------------------------------------------------------------------
    # Phase 18 — billing / subscriptions
    # ------------------------------------------------------------------
    subscription_tier = Column(String, default="free", nullable=False)  # "free" | "pro" | "prime"
    subscription_status = Column(String, default="active", nullable=False)  # "active" | "cancelled" | "expired"

    # First time this user ever subscribed to ANY paid tier. Anchors the
    # 12-month first-year-discount window — it does NOT reset if they
    # upgrade/downgrade between pro and prime, only if they lapse back to
    # free and resubscribe fresh (handled in billing logic, not here).
    subscription_started_at = Column(DateTime, nullable=True)

    # End of the CURRENT paid billing period (used to check access, and to
    # know when a renewal charge is due).
    subscription_expires_at = Column(DateTime, nullable=True)

    paystack_customer_code = Column(String, nullable=True)
    # Saved card authorization — required to charge recurring renewals
    # without asking the user to re-enter card details every month.
    paystack_authorization_code = Column(String, nullable=True)

    # Daily activity counter for the free/pro limits. Resets when
    # daily_activity_date no longer matches today's date (UTC).
    daily_activity_count = Column(Integer, default=0, nullable=False)
    daily_activity_date = Column(Date, nullable=True)

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
