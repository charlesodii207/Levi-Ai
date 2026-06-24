from pydantic import BaseModel
from typing import Optional


class ChatRequest(BaseModel):
    conversation_id: int
    message: str


class ChatResponse(BaseModel):
    reply: str