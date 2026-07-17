from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel


class AdminLogin(BaseModel):
    username: str
    password: str


class AdminCreate(BaseModel):
    username: str
    password: str
    tier: str = "moderator"  # "owner" | "super_admin" | "admin" | "moderator"
    platform_role: Optional[str] = None  # required when tier == "admin"


class AdminChangePassword(BaseModel):
    current_password: str
    new_password: str


class AdminOut(BaseModel):
    id: int
    username: str
    tier: str
    platform_role: Optional[str] = None
    # These three come back as null when the viewer is a Tier 3 peer
    # looking at another Tier 3 admin — see serialize_admin_for_viewer
    # in app/api/admin.py for the masking logic.
    status: Optional[str] = None
    last_login_at: Optional[datetime] = None
    last_login_ip: Optional[str] = None
    last_active_at: Optional[datetime] = None
    must_change_password: bool
    created_at: datetime

    class Config:
        from_attributes = True


class AdminTokenResponse(BaseModel):
    message: str
    access_token: str
    token_type: str
    must_change_password: bool


class UserAdminOut(BaseModel):
    id: int
    username: str
    email: str
    is_active: bool
    is_verified: bool
    created_at: datetime
    last_login_at: Optional[datetime] = None
    last_login_ip: Optional[str] = None
    last_active_at: Optional[datetime] = None

    class Config:
        from_attributes = True