from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.auth.jwt import decode_access_token
from app.database import get_db
from app.models.user import User
from app.models.admin import Admin

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/login")
admin_oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/admin/login")


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
):
    payload = decode_access_token(token)

    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        )

    user_id = payload.get("sub")

    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        )

    try:
        user_id = int(user_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        )

    user = db.query(User).filter(User.id == user_id).first()

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    return user


# ---------------------------------------------------------------------------
# Admin auth
# ---------------------------------------------------------------------------

def _decode_admin_token(token: str, db: Session) -> Admin:
    payload = decode_access_token(token)

    # The "type" claim keeps a stolen user token from ever working
    # against admin routes, and vice versa.
    if payload is None or payload.get("type") != "admin":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid admin token",
        )

    admin_id = payload.get("sub")

    try:
        admin_id = int(admin_id)
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid admin token",
        )

    admin = db.query(Admin).filter(Admin.id == admin_id).first()

    if admin is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Admin not found",
        )

    if admin.status != "active":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This admin account has been blocked.",
        )

    return admin


def get_current_admin_raw(
    token: str = Depends(admin_oauth2_scheme),
    db: Session = Depends(get_db),
) -> Admin:
    """
    Use for the small set of endpoints an admin must reach even before
    changing a forced first-login password: /admin/me, /admin/change-password.
    """
    return _decode_admin_token(token, db)


def get_current_admin(
    admin: Admin = Depends(get_current_admin_raw),
) -> Admin:
    """
    Use for every other admin endpoint. Blocks access until the admin
    has changed their initial password.
    """
    if admin.must_change_password:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You must change your password before continuing.",
        )
    return admin


def require_senior(
    admin: Admin = Depends(get_current_admin),
) -> Admin:
    """Use for senior-only endpoints (managing other admins, deleting users, logs)."""
    if admin.role != "senior":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Senior admin access required.",
        )
    return admin
