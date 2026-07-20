from typing import Optional

from pydantic import BaseModel, EmailStr, field_validator


# ---------- Response Schemas ----------

class UserSettingsOut(BaseModel):
    id: int
    username: str
    email: EmailStr
    bio: Optional[str] = None
    avatar_url: Optional[str] = None
    default_model: str
    theme: str
    email_notifications: bool

    class Config:
        from_attributes = True


# ---------- Request Schemas ----------

class UpdateProfileRequest(BaseModel):
    username: Optional[str] = None
    bio: Optional[str] = None
    avatar_url: Optional[str] = None
    default_model: Optional[str] = None
    theme: Optional[str] = None
    email_notifications: Optional[bool] = None

    @field_validator("default_model")
    @classmethod
    def validate_model(cls, v):
        if v is not None and v not in ("swift", "nova"):
            raise ValueError("default_model must be 'swift' or 'nova'")
        return v

    @field_validator("theme")
    @classmethod
    def validate_theme(cls, v):
        if v is not None and v not in ("light", "dark"):
            raise ValueError("theme must be 'light' or 'dark'")
        return v


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


class RequestEmailChange(BaseModel):
    new_email: EmailStr


class VerifyEmailChange(BaseModel):
    otp: str


class DeleteAccountRequest(BaseModel):
    password: str
