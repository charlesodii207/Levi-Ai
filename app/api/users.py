from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User

from app.schemas.user import (
    UserCreate,
    UserLogin,
    VerifyOTP,
    ResendOTP,
    TokenResponse,
)

from app.auth.security import hash_password, verify_password
from app.auth.jwt import create_access_token

from app.utils.otp import generate_otp
from app.utils.email import send_otp_email

router = APIRouter()


def to_aware(dt: datetime) -> datetime:
    """Ensure a datetime is timezone-aware (UTC).
    SQLite strips tzinfo on read-back, so we normalise here."""
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


@router.post("/register")
def register(user: UserCreate, db: Session = Depends(get_db)):

    existing_email = db.query(User).filter(
        User.email == user.email
    ).first()

    if existing_email:
        raise HTTPException(
            status_code=400,
            detail="Email already exists"
        )

    existing_username = db.query(User).filter(
        User.username == user.username
    ).first()

    if existing_username:
        raise HTTPException(
            status_code=400,
            detail="Username already exists"
        )

    otp = generate_otp()

    new_user = User(
        username=user.username,
        email=user.email,
        hashed_password=hash_password(user.password),
        is_verified=False,
        otp_code=otp,
        otp_expiry=datetime.now(timezone.utc) + timedelta(minutes=10)
    )

    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    try:
        send_otp_email(
            receiver_email=user.email,
            otp=otp
        )
    except Exception:
        db.delete(new_user)
        db.commit()

        raise HTTPException(
            status_code=500,
            detail="Failed to send verification email."
        )

    return {
        "message": (
            "Registration successful. "
            "Please check your email for the OTP."
        ),
        "email": new_user.email
    }


@router.post("/verify-email", response_model=TokenResponse)
def verify_email(
    data: VerifyOTP,
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(
        User.email == data.email
    ).first()

    if not user:
        raise HTTPException(
            status_code=404,
            detail="User not found"
        )

    if user.is_verified:
        access_token = create_access_token(
            {"sub": str(user.id)}
        )
        return {
            "message": "Email already verified.",
            "access_token": access_token,
            "token_type": "bearer"
        }

    if user.otp_code != data.otp:
        raise HTTPException(
            status_code=400,
            detail="Invalid OTP"
        )

    # Normalise to aware before comparing — SQLite returns naive datetimes
    otp_expiry = to_aware(user.otp_expiry)

    if otp_expiry is None or otp_expiry < datetime.now(timezone.utc):
        raise HTTPException(
            status_code=400,
            detail="OTP has expired"
        )

    user.is_verified = True
    user.otp_code = None
    user.otp_expiry = None

    db.commit()
    db.refresh(user)

    access_token = create_access_token(
        {"sub": str(user.id)}
    )

    return {
        "message": "Email verified successfully.",
        "access_token": access_token,
        "token_type": "bearer"
    }


@router.post("/resend-otp")
def resend_otp(
    data: ResendOTP,
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(
        User.email == data.email
    ).first()

    # Generic response prevents email enumeration
    if not user or user.is_verified:
        return {
            "message": (
                "If the email exists and is not verified, "
                "a new OTP has been sent."
            )
        }

    # TODO: Add rate limiting (1 request every 60 seconds)

    otp = generate_otp()

    user.otp_code = otp
    user.otp_expiry = datetime.now(timezone.utc) + timedelta(minutes=10)

    db.commit()

    try:
        send_otp_email(
            receiver_email=user.email,
            otp=otp
        )
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="Failed to send OTP email."
        )

    return {
        "message": (
            "If the email exists and is not verified, "
            "a new OTP has been sent."
        )
    }


@router.post("/login", response_model=TokenResponse)
def login(
    user: UserLogin,
    db: Session = Depends(get_db)
):
    db_user = db.query(User).filter(
        User.email == user.email
    ).first()

    if not db_user:
        raise HTTPException(
            status_code=400,
            detail="Invalid email or password"
        )

    if not verify_password(
        user.password,
        db_user.hashed_password
    ):
        raise HTTPException(
            status_code=400,
            detail="Invalid email or password"
        )

    if not db_user.is_active:
        raise HTTPException(
            status_code=400,
            detail="Your account has been disabled."
        )

    if not db_user.is_verified:
        raise HTTPException(
            status_code=400,
            detail="Please verify your email first."
        )

    access_token = create_access_token(
        {"sub": str(db_user.id)}
    )

    return {
        "message": "Login successful.",
        "access_token": access_token,
        "token_type": "bearer"
    }


@router.get("/me")
def get_me(current_user: User = Depends(get_current_user)):
    return {
        "id": current_user.id,
        "username": current_user.username,
        "email": current_user.email,
        "is_active": current_user.is_active,
        "verified": current_user.is_verified,
        "created_at": current_user.created_at,
    }
