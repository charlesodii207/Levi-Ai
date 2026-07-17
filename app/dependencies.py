from datetime import datetime, timezone

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.auth.jwt import decode_access_token
from app.database import get_db
from app.models.user import User
from app.models.admin import Admin
from app.core.tiers import rank

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

    # A suspended user's existing token must stop working immediately,
    # not just at their next login attempt.
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your account has been suspended.",
        )

    # Powers real "online now" status — updated on every authenticated
    # request, not just at login.
    user.last_active_at = datetime.now(timezone.utc)
    db.commit()

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

    admin.last_active_at = datetime.now(timezone.utc)
    db.commit()

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


def require_tier(*allowed_tiers: str):
    """
    Dependency factory — restricts a route to specific tiers.
    Usage: admin: Admin = Depends(require_tier("owner", "super_admin"))
    """
    def _check(admin: Admin = Depends(get_current_admin)) -> Admin:
        if admin.tier not in allowed_tiers:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to access this resource.",
            )
        return admin
    return _check


def require_max_rank(max_rank: int):
    """
    Dependency factory — restricts a route to any tier at or above a
    given authority level (rank 1 = Owner is the highest authority,
    so "at or above" means rank <= max_rank).
    Usage: admin: Admin = Depends(require_max_rank(2))  # owner or super_admin
    """
    def _check(admin: Admin = Depends(get_current_admin)) -> Admin:
        if rank(admin.tier) > max_rank:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to access this resource.",
            )
        return admin
    return _check


# Convenience shortcuts for the most common checks
require_owner = require_tier("owner")
require_owner_or_super = require_tier("owner", "super_admin")
require_admin_module_access = require_max_rank(3)  # owner, super_admin, admin — not moderator