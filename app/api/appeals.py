from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.models.suspension_appeal import SuspensionAppeal
from app.schemas.appeal import AppealSubmit

router = APIRouter(prefix="/appeals", tags=["Appeals"])


@router.post("")
def submit_appeal(data: AppealSubmit, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == data.email).first()

    # Generic response either way — don't reveal whether an email
    # exists or whether an account is suspended to an unauthenticated
    # caller (same email-enumeration precaution as forgot-password).
    generic_response = {
        "message": "If that account is suspended, your appeal has been submitted."
    }

    if not user or user.is_active:
        return generic_response

    existing_pending = (
        db.query(SuspensionAppeal)
        .filter(SuspensionAppeal.user_id == user.id, SuspensionAppeal.status == "pending")
        .first()
    )
    if existing_pending:
        # Already has one in the queue — don't create a duplicate,
        # but still return the generic response.
        return generic_response

    if not data.message or not data.message.strip():
        raise HTTPException(status_code=400, detail="Please include a message explaining your appeal.")

    appeal = SuspensionAppeal(
        user_id=user.id,
        email=user.email,
        message=data.message.strip(),
        status="pending",
    )
    db.add(appeal)
    db.commit()

    return generic_response
