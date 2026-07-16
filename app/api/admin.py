from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.admin import Admin
from app.models.admin_action_log import AdminActionLog
from app.models.user import User
from app.schemas.admin import (
    AdminLogin,
    AdminCreate,
    AdminChangePassword,
    AdminOut,
    AdminTokenResponse,
    UserAdminOut,
)
from app.auth.security import hash_password, verify_password
from app.auth.jwt import create_access_token
from app.dependencies import get_current_admin, get_current_admin_raw, require_senior
from app.utils.ip import get_client_ip

router = APIRouter(prefix="/admin", tags=["Admin"])


def log_action(
    db: Session,
    admin: Admin,
    action: str,
    request: Request,
    target_type: str = None,
    target_id: int = None,
    details: str = None,
):
    entry = AdminActionLog(
        admin_id=admin.id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        details=details,
        ip_address=get_client_ip(request),
    )
    db.add(entry)
    db.commit()


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

@router.post("/login", response_model=AdminTokenResponse)
def admin_login(data: AdminLogin, request: Request, db: Session = Depends(get_db)):
    admin = db.query(Admin).filter(Admin.username == data.username).first()

    if not admin or not verify_password(data.password, admin.hashed_password):
        raise HTTPException(status_code=400, detail="Invalid username or password")

    if admin.status != "active":
        raise HTTPException(status_code=403, detail="This admin account has been blocked.")

    admin.last_login_at = datetime.now(timezone.utc)
    admin.last_login_ip = get_client_ip(request)
    db.commit()

    access_token = create_access_token(
        {"sub": str(admin.id), "type": "admin", "role": admin.role}
    )

    return {
        "message": "Login successful.",
        "access_token": access_token,
        "token_type": "bearer",
        "must_change_password": admin.must_change_password,
    }


@router.post("/change-password")
def change_password(
    data: AdminChangePassword,
    request: Request,
    admin: Admin = Depends(get_current_admin_raw),
    db: Session = Depends(get_db),
):
    if not verify_password(data.current_password, admin.hashed_password):
        raise HTTPException(status_code=400, detail="Current password is incorrect.")

    admin.hashed_password = hash_password(data.new_password)
    admin.must_change_password = False
    db.commit()

    log_action(db, admin, "changed_own_password", request)

    return {"message": "Password changed successfully."}


@router.get("/me", response_model=AdminOut)
def get_admin_me(admin: Admin = Depends(get_current_admin_raw)):
    return admin


# ---------------------------------------------------------------------------
# Senior-only — manage other admins
# ---------------------------------------------------------------------------

@router.post("/admins", response_model=AdminOut)
def create_admin(
    data: AdminCreate,
    request: Request,
    senior: Admin = Depends(require_senior),
    db: Session = Depends(get_db),
):
    if data.role not in ("senior", "junior"):
        raise HTTPException(status_code=400, detail="Role must be 'senior' or 'junior'.")

    existing = db.query(Admin).filter(Admin.username == data.username).first()
    if existing:
        raise HTTPException(status_code=400, detail="Username already exists.")

    new_admin = Admin(
        username=data.username,
        hashed_password=hash_password(data.password),
        role=data.role,
        status="active",
        must_change_password=True,
        created_by=senior.id,
    )
    db.add(new_admin)
    db.commit()
    db.refresh(new_admin)

    log_action(db, senior, "created_admin", request, "admin", new_admin.id, f"role={data.role}")

    return new_admin


@router.get("/admins", response_model=List[AdminOut])
def list_admins(
    senior: Admin = Depends(require_senior),
    db: Session = Depends(get_db),
):
    return db.query(Admin).order_by(Admin.created_at.desc()).all()


@router.post("/admins/{admin_id}/block")
def block_admin(
    admin_id: int,
    request: Request,
    senior: Admin = Depends(require_senior),
    db: Session = Depends(get_db),
):
    target = db.query(Admin).filter(Admin.id == admin_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="Admin not found.")
    if target.id == senior.id:
        raise HTTPException(status_code=400, detail="You can't block your own account.")

    target.status = "blocked"
    db.commit()

    log_action(db, senior, "blocked_admin", request, "admin", target.id)

    return {"message": f"Admin '{target.username}' has been blocked."}


@router.post("/admins/{admin_id}/unblock")
def unblock_admin(
    admin_id: int,
    request: Request,
    senior: Admin = Depends(require_senior),
    db: Session = Depends(get_db),
):
    target = db.query(Admin).filter(Admin.id == admin_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="Admin not found.")

    target.status = "active"
    db.commit()

    log_action(db, senior, "unblocked_admin", request, "admin", target.id)

    return {"message": f"Admin '{target.username}' has been unblocked."}


@router.get("/logs")
def get_action_logs(
    senior: Admin = Depends(require_senior),
    db: Session = Depends(get_db),
    limit: int = 100,
):
    logs = (
        db.query(AdminActionLog)
        .order_by(AdminActionLog.created_at.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "id": log.id,
            "admin_id": log.admin_id,
            "action": log.action,
            "target_type": log.target_type,
            "target_id": log.target_id,
            "details": log.details,
            "ip_address": log.ip_address,
            "created_at": log.created_at,
        }
        for log in logs
    ]


# ---------------------------------------------------------------------------
# Shared (senior + junior) — manage regular users
# ---------------------------------------------------------------------------

@router.get("/users", response_model=List[UserAdminOut])
def list_users(
    admin: Admin = Depends(get_current_admin),
    db: Session = Depends(get_db),
    skip: int = 0,
    limit: int = 50,
):
    return (
        db.query(User)
        .order_by(User.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )


@router.get("/users/{user_id}", response_model=UserAdminOut)
def get_user(
    user_id: int,
    admin: Admin = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    return user


@router.post("/users/{user_id}/suspend")
def suspend_user(
    user_id: int,
    request: Request,
    admin: Admin = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    user.is_active = False
    db.commit()

    log_action(db, admin, "suspended_user", request, "user", user.id)

    return {"message": f"User '{user.username}' has been suspended."}


@router.post("/users/{user_id}/activate")
def activate_user(
    user_id: int,
    request: Request,
    admin: Admin = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    user.is_active = True
    db.commit()

    log_action(db, admin, "activated_user", request, "user", user.id)

    return {"message": f"User '{user.username}' has been reactivated."}


@router.delete("/users/{user_id}")
def delete_user(
    user_id: int,
    request: Request,
    senior: Admin = Depends(require_senior),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    username = user.username
    db.delete(user)
    db.commit()

    log_action(db, senior, "deleted_user", request, "user", user_id, f"username={username}")

    return {"message": f"User '{username}' has been permanently deleted."}


# ---------------------------------------------------------------------------
# Overview stats
# ---------------------------------------------------------------------------

@router.get("/stats/overview")
def get_overview_stats(
    admin: Admin = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    total_users = db.query(User).count()
    active_users = db.query(User).filter(User.is_active == True).count()
    verified_users = db.query(User).filter(User.is_verified == True).count()

    return {
        "total_users": total_users,
        "active_users": active_users,
        "suspended_users": total_users - active_users,
        "verified_users": verified_users,
        "unverified_users": total_users - verified_users,
    }
