from typing import Optional

from pydantic import BaseModel


class SubscribeRequest(BaseModel):
    tier: str  # "pro" | "prime"


class SubscribeResponse(BaseModel):
    authorization_url: str
    reference: str


class BillingStatusOut(BaseModel):
    tier: str
    status: str
    expires_at: Optional[str] = None
    daily_activity_count: int
    daily_limit: Optional[int] = None


class PlanOut(BaseModel):
    name: str
    price_usd: float
    original_price_usd: Optional[float] = None
    discount_percent: Optional[int] = None
    daily_limit: Optional[int] = None
    models: list[str]
    extras: list[str] = []
