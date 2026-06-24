from pydantic import BaseModel, EmailStr


# ---------- Request Schemas ----------

class UserCreate(BaseModel):
    username: str
    email: EmailStr
    password: str


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class VerifyOTP(BaseModel):
    email: EmailStr
    otp: str


class ResendOTP(BaseModel):
    email: EmailStr


# ---------- Response Schemas ----------

class RegisterResponse(BaseModel):
    message: str
    email: EmailStr


class TokenResponse(BaseModel):
    message: str
    access_token: str
    token_type: str


class UserResponse(BaseModel):
    id: int
    username: str
    email: EmailStr
    is_active: bool
    verified: bool

    class Config:
        from_attributes = True