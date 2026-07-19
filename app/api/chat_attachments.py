"""
Add this route to your existing knowledge_base.py router (or a new
chat_attachments.py router — either works, just make sure it's included
in app.main).

This endpoint is deliberately separate from POST /knowledge/upload:
- /knowledge/upload -> permanent, saved to the KnowledgeBase table, shows
  up on the /knowledge page, searchable later.
- /chat/attach (this one) -> one-off, scoped to a single message, matching
  how ChatGPT/Claude treat casual chat attachments vs. persistent project/
  knowledge files. Nothing is written to the database or Supabase storage.

Images are handled differently from documents: rather than extracting text
via OCR, images go through the currently selected model's vision capability
(checked by provider, not by model name — see ai_service.model_supports_vision).
If the active model can't see images, this returns a clear, friendly error
instead of silently failing or producing a meaningless empty description.
"""

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from pydantic import BaseModel
from typing import Optional

from app.api.users import get_current_user
from app.models.user import User
from app.services.extraction_service import extract_text
from app.services.ai_service import analyze_image, model_supports_vision, model_display_name

router = APIRouter(prefix="/chat", tags=["Chat Attachments"])

ALLOWED_EXTS = [".pdf", ".docx", ".txt", ".png", ".jpg", ".jpeg", ".webp", ".bmp"]
IMAGE_EXTS = [".png", ".jpg", ".jpeg", ".webp", ".bmp"]
IMAGE_MIME_PREFIXES = ("image/",)

MAX_ATTACHMENT_SIZE = 20 * 1024 * 1024  # 20MB — smaller than KB uploads since this is ephemeral

# Cap how much extracted text gets sent back — a huge file shouldn't blow
# out the chat prompt's token budget in one shot.
MAX_ATTACHMENT_CHARS = 8000


class AttachmentOut(BaseModel):
    filename: str
    file_size: int
    content: str
    truncated: bool
    is_image: bool = False


def _is_image(filename: str, content_type: str) -> bool:
    if content_type and content_type.startswith(IMAGE_MIME_PREFIXES):
        return True
    lower = filename.lower()
    return any(lower.endswith(ext) for ext in IMAGE_EXTS)


@router.post("/attach", response_model=AttachmentOut)
async def attach_file_to_chat(
    file: UploadFile = File(...),
    model: Optional[str] = Form("swift"),
    current_user: User = Depends(get_current_user),
):
    """Extract content from a file for one-off use in a single chat message.
    Nothing is persisted — the caller is responsible for including the
    returned `content` in that message's prompt context.

    For images, `content` is a genuine visual analysis from the active
    model (if it supports vision) rather than OCR'd text. If the active
    model can't see images, this raises a clear 422 explaining that,
    naming the model, so the frontend can surface it as a normal error
    message rather than a silent failure."""

    filename = file.filename or "unknown"
    if not any(filename.lower().endswith(ext) for ext in ALLOWED_EXTS):
        raise HTTPException(
            status_code=400,
            detail="File type not supported. Allowed: PDF, Word, Text, Images",
        )

    file_bytes = await file.read()

    if len(file_bytes) > MAX_ATTACHMENT_SIZE:
        raise HTTPException(status_code=400, detail="File too large. Maximum size is 20MB.")

    content_type = file.content_type or ""
    is_image = _is_image(filename, content_type)

    if is_image:
        if not model_supports_vision(model):
            display_name = model_display_name(model)
            raise HTTPException(
                status_code=422,
                detail=(
                    f"{display_name} is a text-only chat model right now and can't view images. "
                    f"Switch to Levi Nova to analyze photos."
                ),
            )

        try:
            description = analyze_image(
                file_bytes,
                content_type or "image/jpeg",
                "Describe this image in detail — what it shows, any text visible, "
                "and anything notable about it. Be thorough and specific.",
                model,
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to analyze image: {str(e)}")

        truncated = len(description) > MAX_ATTACHMENT_CHARS
        return AttachmentOut(
            filename=filename,
            file_size=len(file_bytes),
            content=description[:MAX_ATTACHMENT_CHARS],
            truncated=truncated,
            is_image=True,
        )

    # Non-image documents: existing text extraction path, unchanged.
    try:
        extracted_text = extract_text(file_bytes, filename, content_type)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to process file: {str(e)}")

    truncated = len(extracted_text) > MAX_ATTACHMENT_CHARS
    content = extracted_text[:MAX_ATTACHMENT_CHARS]

    return AttachmentOut(
        filename=filename,
        file_size=len(file_bytes),
        content=content,
        truncated=truncated,
        is_image=False,
    )
