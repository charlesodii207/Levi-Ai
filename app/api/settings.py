from datetime import datetime, timedelta, timezone
import random

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.api.users import get_current_user
from app.models.user import User
from app.schemas.settings import (
    UserSettingsOut,
    UpdateProfileRequest,
    ChangePasswordRequest,
    RequestEmailChange,
    VerifyEmailChange,
    DeleteAccountRequest,
)

# NOTE: adjust this import to wherever your password hashing helpers
# actually live (e.g. app.auth.security, app.core.security, app.auth.jwt)
from app.auth.security import verify_password, hash_password

router = APIRouter(prefix="/settings", tags=["Settings"])


# ── Routes ────────────────────────────────────────────────────────────────

@router.get("/", response_model=UserSettingsOut)
def get_settings(current_user: User = Depends(get_current_user)):
    return current_user


@router.patch("/profile", response_model=UserSettingsOut)
def update_profile(
    body: UpdateProfileRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    data = body.model_dump(exclude_unset=True)

    if "username" in data and data["username"] != current_user.username:
        existing = db.query(User).filter(
            User.username == data["username"],
            User.id != current_user.id,
        ).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Username already taken",
            )

    for field, value in data.items():
        setattr(current_user, field, value)

    db.commit()
    db.refresh(current_user)
    return current_user


@router.post("/change-password")
def change_password(
    body: ChangePasswordRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not verify_password(body.current_password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect",
        )

    current_user.hashed_password = hash_password(body.new_password)
    db.commit()
    return {"message": "Password updated successfully"}


@router.post("/change-email/request")
def request_email_change(
    body: RequestEmailChange,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    existing = db.query(User).filter(User.email == body.new_email).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already in use",
        )

    otp = f"{random.randint(0, 999999):06d}"
    current_user.pending_email = body.new_email
    current_user.otp_code = otp
    current_user.otp_expiry = datetime.now(timezone.utc) + timedelta(minutes=10)
    db.commit()

    # TODO: wire this into whatever email-sending service you already
    # use for registration OTPs, e.g.:
    # send_otp_email(body.new_email, otp)

    return {"message": f"Verification code sent to {body.new_email}"}


@router.post("/change-email/verify")
def verify_email_change(
    body: VerifyEmailChange,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not current_user.pending_email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No pending email change",
        )

    if (
        current_user.otp_code != body.otp
        or current_user.otp_expiry is None
        or current_user.otp_expiry < datetime.now(timezone.utc)
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired code",
        )

    current_user.email = current_user.pending_email
    current_user.pending_email = None
    current_user.otp_code = None
    current_user.otp_expiry = None
    db.commit()

    return {"message": "Email updated successfully"}


@router.delete("/account")
def delete_account(
    body: DeleteAccountRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not verify_password(body.password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Incorrect password",
        )

    db.delete(current_user)
    db.commit()
    return {"message": "Account deleted"}
