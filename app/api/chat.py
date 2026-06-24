from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.dependencies import get_current_user

from app.models.user import User
from app.models.conversation import Conversation
from app.models.message import Message

from app.schemas.chat import ChatRequest, ChatResponse

from app.services.ai_service import generate_response
from app.services.memory_service import MemoryService
from app.services.memory_extractor import extract_memory

router = APIRouter(
    prefix="/chat",
    tags=["Chat"]
)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.post("/", response_model=ChatResponse)
def chat(
    request: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    conversation = (
        db.query(Conversation)
        .filter(
            Conversation.id == request.conversation_id,
            Conversation.user_id == current_user.id
        )
        .first()
    )

    if not conversation:
        raise HTTPException(
            status_code=404,
            detail="Conversation not found."
        )

    # -----------------------------------
    # Save memory if the message contains one
    # -----------------------------------

    key, value = extract_memory(request.message)

    if key:
        MemoryService.save_memory(
            db=db,
            user_id=current_user.id,
            key=key,
            value=value
        )

    # -----------------------------------
    # Load conversation history
    # -----------------------------------

    history = (
        db.query(Message)
        .filter(Message.conversation_id == conversation.id)
        .order_by(Message.created_at.asc())
        .all()
    )

    messages = []

    # -----------------------------------
    # Load user memories
    # -----------------------------------

    memories = MemoryService.get_memories(
        db=db,
        user_id=current_user.id
    )

    if memories:

        memory_text = "User memories:\n"

        for memory in memories:
            memory_text += f"- {memory.key}: {memory.value}\n"

        messages.append({
            "role": "system",
            "content": memory_text
        })

    # -----------------------------------
    # Previous conversation
    # -----------------------------------

    for msg in history:
        messages.append({
            "role": msg.role,
            "content": msg.content
        })

    messages.append({
        "role": "user",
        "content": request.message
    })

    reply = generate_response(messages)

    # Save user message
    user_message = Message(
        conversation_id=conversation.id,
        role="user",
        content=request.message
    )

    # Save AI reply
    assistant_message = Message(
        conversation_id=conversation.id,
        role="assistant",
        content=reply
    )

    db.add(user_message)
    db.add(assistant_message)

    db.commit()

    return ChatResponse(reply=reply)