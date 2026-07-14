from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Optional
import json
import threading

from app.database import get_db
from app.models.conversation import Conversation
from app.models.message import Message
from app.api.users import get_current_user
from app.models.user import User
from app.services.ai_service import generate_response, generate_response_stream, generate_title
from app.services.memory_service import get_user_memories, format_memories_for_prompt, extract_and_save_memories

router = APIRouter(prefix="/chat", tags=["Chat"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str
    conversation_id: Optional[int] = None
    stream: bool = False
    mode_prompt: Optional[str] = None


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

def get_conversation_or_404(conversation_id: int, user: User, db: Session) -> Conversation:
    conv = db.query(Conversation).filter(
        Conversation.id == conversation_id,
        Conversation.user_id == user.id
    ).first()
    if not conv:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
    return conv


def build_system_prompt(mode_prompt: Optional[str], memories: list[dict]) -> Optional[str]:
    """Build system prompt with memories injected."""
    memory_context = format_memories_for_prompt(memories)
    if mode_prompt:
        return mode_prompt + memory_context
    if memory_context:
        return memory_context
    return None


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post("/", response_model=ChatResponse)
def chat(
    request: ChatRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # 1. Get or create conversation
    if request.conversation_id:
        conversation = get_conversation_or_404(request.conversation_id, current_user, db)
    else:
        conversation = Conversation(user_id=current_user.id, title="New Chat")
        db.add(conversation)
        db.flush()

    # 2. Load conversation history
    history_rows = db.query(Message).filter(
        Message.conversation_id == conversation.id
    ).order_by(Message.created_at.asc()).all()
    history = [{"role": m.role, "content": m.content} for m in history_rows]

    # 3. Load user memories and inject into prompt
    memories = get_user_memories(current_user.id, db)
    memory_context = format_memories_for_prompt(memories)
    if memory_context:
        history = [{"role": "system", "content": memory_context}] + history

    # 4. Save user message
    user_msg = Message(conversation_id=conversation.id, role="user", content=request.message)
    db.add(user_msg)
    db.flush()

    # 5. Generate AI response
    ai_reply = generate_response(request.message, history)

    # 6. Save assistant message
    assistant_msg = Message(conversation_id=conversation.id, role="assistant", content=ai_reply)
    db.add(assistant_msg)

    # 7. Auto-title on first message
    if len(history) == 0:
        conversation.title = generate_title(request.message)

    db.commit()
    db.refresh(conversation)
    db.refresh(assistant_msg)

    # 8. Extract memories in background (non-blocking)
    def extract_memories_bg():
        from app.database import SessionLocal
        bg_db = SessionLocal()
        try:
            extract_and_save_memories(current_user.id, request.message, ai_reply, bg_db)
        finally:
            bg_db.close()

    thread = threading.Thread(target=extract_memories_bg)
    thread.daemon = True
    thread.start()

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

    # 3. Load memories and inject
    memories = get_user_memories(current_user.id, db)
    memory_context = format_memories_for_prompt(memories)
    if memory_context:
        history = [{"role": "system", "content": memory_context}] + history

    # 4. Save user message
    user_msg = Message(conversation_id=conversation.id, role="user", content=request.message)
    db.add(user_msg)
    db.flush()
    db.commit()

    conv_id = conversation.id
    conv_title = conversation.title
    user_id = current_user.id
    user_message = request.message

    def stream_generator():
        full_response = ""

        yield f"data: {json.dumps({'type': 'meta', 'conversation_id': conv_id, 'title': conv_title})}\n\n"

        for chunk in generate_response_stream(user_message, history):
            full_response += chunk
            yield f"data: {json.dumps({'type': 'chunk', 'text': chunk})}\n\n"

        # Save response + extract memories
        new_db = next(get_db())
        try:
            assistant_msg = Message(
                conversation_id=conv_id,
                role="assistant",
                content=full_response
            )
            new_db.add(assistant_msg)

            if is_first_message:
                title = generate_title(user_message)
                conv = new_db.query(Conversation).filter(Conversation.id == conv_id).first()
                if conv:
                    conv.title = title
                    yield f"data: {json.dumps({'type': 'title', 'title': title})}\n\n"

            new_db.commit()

            # Extract memories in background
            def extract_bg():
                from app.database import SessionLocal
                bg_db = SessionLocal()
                try:
                    extract_and_save_memories(user_id, user_message, full_response, bg_db)
                finally:
                    bg_db.close()

            thread = threading.Thread(target=extract_bg)
            thread.daemon = True
            thread.start()

        finally:
            new_db.close()

        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(
        stream_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    )


@router.get("/conversations", response_model=list[ConversationOut])
def list_conversations(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    conversations = db.query(Conversation).filter(
        Conversation.user_id == current_user.id
    ).order_by(Conversation.updated_at.desc()).all()

    return [
        ConversationOut(
            id=c.id, title=c.title,
            created_at=str(c.created_at), updated_at=str(c.updated_at),
        )
        for c in conversations
    ]


@router.get("/conversations/{conversation_id}", response_model=list[MessageOut])
def get_conversation_messages(
    conversation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    conversation = get_conversation_or_404(conversation_id, current_user, db)
    messages = db.query(Message).filter(
        Message.conversation_id == conversation.id
    ).order_by(Message.created_at.asc()).all()

    return [
        MessageOut(
            id=m.id, role=m.role, content=m.content, created_at=str(m.created_at)
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
    conversation = get_conversation_or_404(conversation_id, current_user, db)
    db.delete(conversation)
    db.commit()
    return {"message": "Conversation deleted"}


@router.delete("/conversations")
def delete_all_conversations(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    conversations = db.query(Conversation).filter(
        Conversation.user_id == current_user.id
    ).all()
    for conv in conversations:
        db.delete(conv)
    db.commit()
    return {"message": f"Deleted {len(conversations)} conversation(s)"}
