from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr


class AppealSubmit(BaseModel):
    email: EmailStr
    message: str


class AppealOut(BaseModel):
    id: int
    user_id: int
    email: str
    message: str
    status: str
    created_at: datetime
    resolved_at: Optional[datetime] = None
    resolved_by: Optional[int] = None

    class Config:
        from_attributes = True
