"""
Add this route to your existing knowledge_base.py router (or a new
chat_attachments.py router — either works, just make sure it's included
in app.main).

This endpoint is deliberately separate from POST /knowledge/upload:
- /knowledge/upload -> permanent, saved to the KnowledgeBase table, shows
  up on the /knowledge page, searchable later.
- /chat/attach (this one) -> one-off, extracts text and returns it
  immediately, nothing is written to the database or Supabase storage.
  Scoped to a single message, matching how ChatGPT/Claude treat casual
  chat attachments vs. persistent project/knowledge files.
"""

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel

from app.api.users import get_current_user
from app.models.user import User
from app.services.extraction_service import extract_text

router = APIRouter(prefix="/chat", tags=["Chat Attachments"])

ALLOWED_EXTS = [".pdf", ".docx", ".txt", ".png", ".jpg", ".jpeg", ".webp", ".bmp"]
MAX_ATTACHMENT_SIZE = 20 * 1024 * 1024  # 20MB — smaller than KB uploads since this is ephemeral

# Cap how much extracted text gets sent back — a huge file shouldn't blow
# out the chat prompt's token budget in one shot.
MAX_ATTACHMENT_CHARS = 8000


class AttachmentOut(BaseModel):
    filename: str
    file_size: int
    content: str
    truncated: bool


@router.post("/attach", response_model=AttachmentOut)
async def attach_file_to_chat(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):
    """Extract text from a file for one-off use in a single chat message.
    Nothing is persisted — the caller is responsible for including the
    returned `content` in that message's prompt context."""

    filename = file.filename or "unknown"
    if not any(filename.lower().endswith(ext) for ext in ALLOWED_EXTS):
        raise HTTPException(
            status_code=400,
            detail="File type not supported. Allowed: PDF, Word, Text, Images",
        )

    file_bytes = await file.read()

    if len(file_bytes) > MAX_ATTACHMENT_SIZE:
        raise HTTPException(status_code=400, detail="File too large. Maximum size is 20MB.")

    try:
        extracted_text = extract_text(file_bytes, filename, file.content_type or "")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to process file: {str(e)}")

    truncated = len(extracted_text) > MAX_ATTACHMENT_CHARS
    content = extracted_text[:MAX_ATTACHMENT_CHARS]

    return AttachmentOut(
        filename=filename,
        file_size=len(file_bytes),
        content=content,
        truncated=truncated,
    )
