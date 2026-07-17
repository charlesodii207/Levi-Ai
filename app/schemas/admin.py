from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel


class AdminLogin(BaseModel):
    username: str
    password: str


class AdminCreate(BaseModel):
    username: str
    password: str
    role: str = "junior"  # senior can create "junior" or another "senior"


class AdminChangePassword(BaseModel):
    current_password: str
    new_password: str


class AdminOut(BaseModel):
    id: int
    username: str
    role: str
    status: str
    must_change_password: bool
    created_at: datetime
    last_login_at: Optional[datetime] = None
    last_login_ip: Optional[str] = None
    last_active_at: Optional[datetime] = None  # NEW — powers online dot

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
    last_active_at: Optional[datetime] = None  # NEW — powers online dot

    class Config:
        from_attributes = True
