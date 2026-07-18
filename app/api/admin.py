from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.admin import Admin
from app.models.admin_action_log import AdminActionLog
from app.models.user import User
from app.models.suspension_appeal import SuspensionAppeal
from app.schemas.admin import (
    AdminLogin,
    AdminCreate,
    AdminChangePassword,
    AdminOut,
    AdminTokenResponse,
    UserAdminOut,
)
from app.schemas.appeal import AppealOut
from app.auth.security import hash_password, verify_password
from app.auth.jwt import create_access_token
from app.dependencies import (
    get_current_admin,
    get_current_admin_raw,
    require_owner_or_super,
    require_admin_module_access,
)
from app.utils.ip import get_client_ip
from app.core.tiers import (
    VALID_TIERS,
    PLATFORM_ROLES,
    can_create,
    can_manage,
    can_delete_admin,
    can_promote_demote,
    can_delete_user,
    can_reset_password,
    visible_tiers_for,
)
import secrets
import string

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


def serialize_admin_for_viewer(viewer: Admin, target: Admin) -> dict:
    """
    Builds the admin dict returned to the frontend, masking peer-level
    data per the visibility model: a Tier 3 (Administrator) viewing
    another Tier 3 peer sees everything except Status, Last IP, and
    Last Active — those are only visible for Tier 4 (Moderator) records
    or when the viewer outranks the target.
    """
    data = {
        "id": target.id,
        "username": target.username,
        "tier": target.tier,
        "platform_role": target.platform_role,
        "status": target.status,
        "must_change_password": target.must_change_password,
        "created_at": target.created_at,
        "last_login_at": target.last_login_at,
        "last_login_ip": target.last_login_ip,
        "last_active_at": target.last_active_at,
    }

    is_peer_tier3 = viewer.tier == "admin" and target.tier == "admin" and viewer.id != target.id
    if is_peer_tier3:
        data["status"] = None
        data["last_login_ip"] = None
        data["last_active_at"] = None

    return data


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
        {"sub": str(admin.id), "type": "admin", "tier": admin.tier}
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
# Admin management
# ---------------------------------------------------------------------------

@router.post("/admins", response_model=AdminOut)
def create_admin(
    data: AdminCreate,
    request: Request,
    actor: Admin = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    if data.tier not in VALID_TIERS:
        raise HTTPException(status_code=400, detail="Invalid tier.")

    if not can_create(actor.tier, data.tier):
        raise HTTPException(
            status_code=403,
            detail="You don't have permission to create an admin at that tier.",
        )

    if data.tier == "admin":
        if not data.platform_role or data.platform_role not in PLATFORM_ROLES:
            raise HTTPException(
                status_code=400,
                detail=f"Administrator accounts require a platform_role, one of: {', '.join(PLATFORM_ROLES)}.",
            )
    else:
        data.platform_role = None  # only Tier 3 carries a platform role

    existing = db.query(Admin).filter(Admin.username == data.username).first()
    if existing:
        raise HTTPException(status_code=400, detail="Username already exists.")

    new_admin = Admin(
        username=data.username,
        hashed_password=hash_password(data.password),
        tier=data.tier,
        platform_role=data.platform_role,
        status="active",
        must_change_password=True,
        created_by=actor.id,
    )
    db.add(new_admin)
    db.commit()
    db.refresh(new_admin)

    log_action(db, actor, "created_admin", request, "admin", new_admin.id, f"tier={data.tier}")

    return new_admin


@router.get("/admins", response_model=List[AdminOut])
def list_admins(
    actor: Admin = Depends(require_admin_module_access),
    db: Session = Depends(get_db),
):
    allowed_tiers = visible_tiers_for(actor.tier)
    if not allowed_tiers:
        raise HTTPException(status_code=403, detail="You don't have access to the Admins module.")

    admins = (
        db.query(Admin)
        .filter(Admin.tier.in_(allowed_tiers))
        .order_by(Admin.created_at.desc())
        .all()
    )
    return [serialize_admin_for_viewer(actor, a) for a in admins]


class ChangeTierRequest(BaseModel):
    new_tier: str
    platform_role: Optional[str] = None


@router.post("/admins/{admin_id}/change-tier")
def change_admin_tier(
    admin_id: int,
    data: ChangeTierRequest,
    request: Request,
    actor: Admin = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    if data.new_tier not in VALID_TIERS:
        raise HTTPException(status_code=400, detail="Invalid tier.")

    target = db.query(Admin).filter(Admin.id == admin_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="Admin not found.")

    if not can_promote_demote(actor.tier, target.tier, data.new_tier):
        raise HTTPException(
            status_code=403,
            detail="You don't have permission to change this admin's tier.",
        )

    # Moving someone INTO Administrator requires a department, same
    # rule as account creation. Moving them OUT clears it.
    if data.new_tier == "admin":
        if not data.platform_role or data.platform_role not in PLATFORM_ROLES:
            raise HTTPException(
                status_code=400,
                detail=f"Administrator accounts require a platform_role, one of: {', '.join(PLATFORM_ROLES)}.",
            )
        target.platform_role = data.platform_role
    else:
        target.platform_role = None

    old_tier = target.tier
    target.tier = data.new_tier
    db.commit()

    log_action(
        db, actor, "changed_admin_tier", request, "admin", target.id,
        f"{old_tier} -> {data.new_tier}",
    )

    return {"message": f"'{target.username}' is now {data.new_tier}."}


@router.post("/admins/{admin_id}/block")
def block_admin(
    admin_id: int,
    request: Request,
    actor: Admin = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    target = db.query(Admin).filter(Admin.id == admin_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="Admin not found.")
    if target.id == actor.id:
        raise HTTPException(status_code=400, detail="You can't block your own account.")
    if not can_manage(actor.tier, target.tier):
        raise HTTPException(status_code=403, detail="You don't have permission to block this admin.")

    target.status = "blocked"
    db.commit()

    log_action(db, actor, "blocked_admin", request, "admin", target.id)

    return {"message": f"Admin '{target.username}' has been blocked."}


@router.post("/admins/{admin_id}/unblock")
def unblock_admin(
    admin_id: int,
    request: Request,
    actor: Admin = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    target = db.query(Admin).filter(Admin.id == admin_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="Admin not found.")
    if not can_manage(actor.tier, target.tier):
        raise HTTPException(status_code=403, detail="You don't have permission to unblock this admin.")

    target.status = "active"
    db.commit()

    log_action(db, actor, "unblocked_admin", request, "admin", target.id)

    return {"message": f"Admin '{target.username}' has been unblocked."}


def generate_temp_password(length: int = 12) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


@router.post("/admins/{admin_id}/reset-password")
def reset_admin_password(
    admin_id: int,
    request: Request,
    actor: Admin = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    target = db.query(Admin).filter(Admin.id == admin_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="Admin not found.")

    if not can_reset_password(actor.tier, target.tier):
        raise HTTPException(
            status_code=403,
            detail="You don't have permission to reset this admin's password.",
        )

    temp_password = generate_temp_password()
    target.hashed_password = hash_password(temp_password)
    target.must_change_password = True
    db.commit()

    log_action(db, actor, "reset_admin_password", request, "admin", target.id)

    # Shown once — the actor is responsible for relaying it securely.
    return {
        "message": f"Password for '{target.username}' has been reset.",
        "temporary_password": temp_password,
    }


@router.delete("/admins/{admin_id}")
def delete_admin(
    admin_id: int,
    request: Request,
    actor: Admin = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    target = db.query(Admin).filter(Admin.id == admin_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="Admin not found.")
    if target.id == actor.id:
        raise HTTPException(status_code=400, detail="You can't delete your own account.")
    if not can_delete_admin(actor.tier, target.tier):
        raise HTTPException(status_code=403, detail="You don't have permission to delete this admin.")

    username = target.username
    db.delete(target)
    db.commit()

    log_action(db, actor, "deleted_admin", request, "admin", admin_id, f"username={username}")

    return {"message": f"Admin '{username}' has been permanently deleted."}


@router.get("/logs")
def get_action_logs(
    actor: Admin = Depends(require_owner_or_super),
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
# User management — available to every tier (Moderator included)
# ---------------------------------------------------------------------------

@router.get("/users", response_model=List[UserAdminOut])
def list_users(
    actor: Admin = Depends(get_current_admin),
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
    actor: Admin = Depends(get_current_admin),
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
    actor: Admin = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    user.is_active = False
    db.commit()

    log_action(db, actor, "suspended_user", request, "user", user.id)

    return {"message": f"User '{user.username}' has been suspended."}


@router.post("/users/{user_id}/activate")
def activate_user(
    user_id: int,
    request: Request,
    actor: Admin = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    user.is_active = True
    db.commit()

    log_action(db, actor, "activated_user", request, "user", user.id)

    return {"message": f"User '{user.username}' has been reactivated."}


@router.delete("/users/{user_id}")
def delete_user(
    user_id: int,
    request: Request,
    actor: Admin = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    if not can_delete_user(actor.tier):
        raise HTTPException(status_code=403, detail="You don't have permission to delete users.")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    username = user.username
    db.delete(user)
    db.commit()

    log_action(db, actor, "deleted_user", request, "user", user_id, f"username={username}")

    return {"message": f"User '{username}' has been permanently deleted."}


# ---------------------------------------------------------------------------
# Suspension appeals — Owner, Super Admin, Administrator (not Moderator)
# ---------------------------------------------------------------------------

@router.get("/appeals", response_model=List[AppealOut])
def list_appeals(
    actor: Admin = Depends(require_admin_module_access),
    db: Session = Depends(get_db),
    status: Optional[str] = None,
):
    query = db.query(SuspensionAppeal)
    if status:
        query = query.filter(SuspensionAppeal.status == status)
    return query.order_by(SuspensionAppeal.created_at.desc()).all()


@router.post("/appeals/{appeal_id}/approve")
def approve_appeal(
    appeal_id: int,
    request: Request,
    actor: Admin = Depends(require_admin_module_access),
    db: Session = Depends(get_db),
):
    appeal = db.query(SuspensionAppeal).filter(SuspensionAppeal.id == appeal_id).first()
    if not appeal:
        raise HTTPException(status_code=404, detail="Appeal not found.")
    if appeal.status != "pending":
        raise HTTPException(status_code=400, detail="This appeal has already been resolved.")

    user = db.query(User).filter(User.id == appeal.user_id).first()
    if user:
        user.is_active = True

    appeal.status = "approved"
    appeal.resolved_at = datetime.now(timezone.utc)
    appeal.resolved_by = actor.id
    db.commit()

    log_action(db, actor, "approved_appeal", request, "user", appeal.user_id, f"appeal_id={appeal.id}")

    return {"message": f"Appeal approved. '{appeal.email}' has been reactivated."}


@router.post("/appeals/{appeal_id}/reject")
def reject_appeal(
    appeal_id: int,
    request: Request,
    actor: Admin = Depends(require_admin_module_access),
    db: Session = Depends(get_db),
):
    appeal = db.query(SuspensionAppeal).filter(SuspensionAppeal.id == appeal_id).first()
    if not appeal:
        raise HTTPException(status_code=404, detail="Appeal not found.")
    if appeal.status != "pending":
        raise HTTPException(status_code=400, detail="This appeal has already been resolved.")

    appeal.status = "rejected"
    appeal.resolved_at = datetime.now(timezone.utc)
    appeal.resolved_by = actor.id
    db.commit()

    log_action(db, actor, "rejected_appeal", request, "user", appeal.user_id, f"appeal_id={appeal.id}")

    return {"message": f"Appeal rejected."}


# ---------------------------------------------------------------------------
# Overview stats
# ---------------------------------------------------------------------------

@router.get("/stats/overview")
def get_overview_stats(
    actor: Admin = Depends(get_current_admin),
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
