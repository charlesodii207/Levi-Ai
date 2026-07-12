from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Optional
import json

from app.database import get_db
from app.models.conversation import Conversation
from app.models.message import Message
from app.api.users import get_current_user
from app.models.user import User
from app.services.ai_service import generate_response, generate_response_stream, generate_title

router = APIRouter(prefix="/chat", tags=["Chat"])


# ── Schemas ──────────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str
    conversation_id: Optional[int] = None  # None = start new conversation
    stream: bool = False                   # True = streaming response


class ChatResponse(BaseModel):
    conversation_id: int
    conversation_title: str
    message_id: int
    response: str


class ConversationOut(BaseModel):
    id: int
    title: str
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True


class MessageOut(BaseModel):
    id: int
    role: str
    content: str
    created_at: str

    class Config:
        from_attributes = True


class RenameRequest(BaseModel):
    title: str


# ── Helper ────────────────────────────────────────────────────────────────────

def get_conversation_or_404(
    conversation_id: int,
    user: User,
    db: Session
) -> Conversation:
    conv = db.query(Conversation).filter(
        Conversation.id == conversation_id,
        Conversation.user_id == user.id
    ).first()
    if not conv:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found"
        )
    return conv


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post("/", response_model=ChatResponse)
def chat(
    request: ChatRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Send a message. Creates a new conversation if conversation_id is not provided.
    """
    # 1. Get or create conversation
    if request.conversation_id:
        conversation = get_conversation_or_404(request.conversation_id, current_user, db)
    else:
        conversation = Conversation(
            user_id=current_user.id,
            title="New Chat"
        )
        db.add(conversation)
        db.flush()  # get the ID before commit

    # 2. Load history from DB
    history_rows = db.query(Message).filter(
        Message.conversation_id == conversation.id
    ).order_by(Message.created_at.asc()).all()

    history = [{"role": m.role, "content": m.content} for m in history_rows]

    # 3. Save user message
    user_msg = Message(
        conversation_id=conversation.id,
        role="user",
        content=request.message
    )
    db.add(user_msg)
    db.flush()

    # 4. Generate AI response with full history context
    ai_reply = generate_response(request.message, history)

    # 5. Save assistant message
    assistant_msg = Message(
        conversation_id=conversation.id,
        role="assistant",
        content=ai_reply
    )
    db.add(assistant_msg)

    # 6. Auto-title on first message
    if len(history) == 0:
        conversation.title = generate_title(request.message)

    db.commit()
    db.refresh(conversation)
    db.refresh(assistant_msg)

    return ChatResponse(
        conversation_id=conversation.id,
        conversation_title=conversation.title,
        message_id=assistant_msg.id,
        response=ai_reply
    )


@router.post("/stream")
def chat_stream(
    request: ChatRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Stream a response token by token using Server-Sent Events (SSE).
    Frontend reads chunks as they arrive for a typing effect.
    """
    # 1. Get or create conversation
    if request.conversation_id:
        conversation = get_conversation_or_404(request.conversation_id, current_user, db)
    else:
        conversation = Conversation(user_id=current_user.id, title="New Chat")
        db.add(conversation)
        db.flush()

    # 2. Load history
    history_rows = db.query(Message).filter(
        Message.conversation_id == conversation.id
    ).order_by(Message.created_at.asc()).all()

    history = [{"role": m.role, "content": m.content} for m in history_rows]
    is_first_message = len(history) == 0

    # 3. Save user message
    user_msg = Message(
        conversation_id=conversation.id,
        role="user",
        content=request.message
    )
    db.add(user_msg)
    db.flush()
    db.commit()

    conv_id = conversation.id
    conv_title = conversation.title

    def stream_generator():
        full_response = ""

        # Send conversation metadata first
        yield f"data: {json.dumps({'type': 'meta', 'conversation_id': conv_id, 'title': conv_title})}\n\n"

        # Stream AI tokens
        for chunk in generate_response_stream(request.message, history):
            full_response += chunk
            yield f"data: {json.dumps({'type': 'chunk', 'text': chunk})}\n\n"

        # Save full response + update title after stream ends
        new_db = next(get_db())
        try:
            assistant_msg = Message(
                conversation_id=conv_id,
                role="assistant",
                content=full_response
            )
            new_db.add(assistant_msg)

            if is_first_message:
                title = generate_title(request.message)
                conv = new_db.query(Conversation).filter(Conversation.id == conv_id).first()
                if conv:
                    conv.title = title
                    yield f"data: {json.dumps({'type': 'title', 'title': title})}\n\n"

            new_db.commit()
        finally:
            new_db.close()

        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(
        stream_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        }
    )


@router.get("/conversations", response_model=list[ConversationOut])
def list_conversations(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get all conversations for the logged-in user, newest first.
    """
    conversations = db.query(Conversation).filter(
        Conversation.user_id == current_user.id
    ).order_by(Conversation.updated_at.desc()).all()

    return [
        ConversationOut(
            id=c.id,
            title=c.title,
            created_at=str(c.created_at),
            updated_at=str(c.updated_at),
        )
        for c in conversations
    ]


@router.get("/conversations/{conversation_id}", response_model=list[MessageOut])
def get_conversation_messages(
    conversation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get all messages in a specific conversation.
    """
    conversation = get_conversation_or_404(conversation_id, current_user, db)

    messages = db.query(Message).filter(
        Message.conversation_id == conversation.id
    ).order_by(Message.created_at.asc()).all()

    return [
        MessageOut(
            id=m.id,
            role=m.role,
            content=m.content,
            created_at=str(m.created_at),
        )
        for m in messages
    ]


@router.patch("/conversations/{conversation_id}/rename")
def rename_conversation(
    conversation_id: int,
    body: RenameRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Rename a conversation.
    """
    conversation = get_conversation_or_404(conversation_id, current_user, db)
    conversation.title = body.title.strip()
    db.commit()
    return {"message": "Conversation renamed", "title": conversation.title}


@router.delete("/conversations/{conversation_id}")
def delete_conversation(
    conversation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Delete a conversation and all its messages.
    """
    conversation = get_conversation_or_404(conversation_id, current_user, db)
    db.delete(conversation)
    db.commit()
    return {"message": "Conversation deleted"}


@router.delete("/conversations")
def delete_all_conversations(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Delete ALL conversations for the current user.
    """
    conversations = db.query(Conversation).filter(
        Conversation.user_id == current_user.id
    ).all()

    for conv in conversations:
        db.delete(conv)

    db.commit()
    return {"message": f"Deleted {len(conversations)} conversation(s)"}