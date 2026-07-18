import os
import uuid
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.models.knowledge_base import KnowledgeBase
from app.services.storage_service import upload_file, delete_file, get_file_url
from app.services.extraction_service import extract_text

router = APIRouter(prefix="/knowledge", tags=["Knowledge Base"])

ALLOWED_TYPES = [
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "text/plain",
    "image/png", "image/jpeg", "image/jpg", "image/webp",
    "image/bmp", "image/tiff",
]

MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB


class DocumentOut(BaseModel):
    id: int
    filename: str
    file_type: str
    file_size: int
    created_at: str

    class Config:
        from_attributes = True


@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Upload a file to the knowledge base."""

    # Validate file type
    content_type = file.content_type or ""
    if not any(allowed in content_type for allowed in ["pdf", "word", "text", "image", "docx"]):
        # Also check by extension
        filename = file.filename or ""
        allowed_exts = [".pdf", ".docx", ".txt", ".png", ".jpg", ".jpeg", ".webp", ".bmp"]
        if not any(filename.lower().endswith(ext) for ext in allowed_exts):
            raise HTTPException(
                status_code=400,
                detail="File type not supported. Allowed: PDF, Word, Text, Images"
            )

    # Read file
    file_bytes = await file.read()

    # Validate file size
    if len(file_bytes) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="File too large. Maximum size is 50MB.")

    # Generate unique storage path
    file_ext = os.path.splitext(file.filename or "file")[1]
    storage_path = f"{current_user.id}/{uuid.uuid4()}{file_ext}"

    # Upload to Supabase
    try:
        upload_file(file_bytes, storage_path, content_type or "application/octet-stream")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to upload file: {str(e)}")

    # Extract text
    extracted_text = extract_text(file_bytes, file.filename or "", content_type)

    # Save to database
    doc = KnowledgeBase(
        user_id=current_user.id,
        filename=file.filename or "unknown",
        file_type=content_type or "unknown",
        file_size=len(file_bytes),
        storage_path=storage_path,
        content=extracted_text,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    return {
        "id": doc.id,
        "filename": doc.filename,
        "file_type": doc.file_type,
        "file_size": doc.file_size,
        "content_preview": extracted_text[:200] + "..." if len(extracted_text) > 200 else extracted_text,
        "created_at": str(doc.created_at),
        "message": "File uploaded and processed successfully"
    }


@router.get("/", response_model=list[DocumentOut])
def list_documents(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all documents in the user's knowledge base."""
    docs = db.query(KnowledgeBase).filter(
        KnowledgeBase.user_id == current_user.id
    ).order_by(KnowledgeBase.created_at.desc()).all()

    return [
        DocumentOut(
            id=d.id,
            filename=d.filename,
            file_type=d.file_type,
            file_size=d.file_size or 0,
            created_at=str(d.created_at),
        )
        for d in docs
    ]


@router.delete("/{doc_id}")
def delete_document(
    doc_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a document from the knowledge base."""
    doc = db.query(KnowledgeBase).filter(
        KnowledgeBase.id == doc_id,
        KnowledgeBase.user_id == current_user.id
    ).first()

    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    # Delete from Supabase storage
    try:
        delete_file(doc.storage_path)
    except Exception:
        pass  # Continue even if storage deletion fails

    db.delete(doc)
    db.commit()

    return {"message": "Document deleted successfully"}


@router.get("/search")
def search_documents(
    query: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Search through the user's knowledge base."""
    docs = db.query(KnowledgeBase).filter(
        KnowledgeBase.user_id == current_user.id,
        KnowledgeBase.content.ilike(f"%{query}%")
    ).limit(5).all()

    results = []
    for doc in docs:
        # Find relevant excerpt
        content = doc.content or ""
        idx = content.lower().find(query.lower())
        if idx >= 0:
            start = max(0, idx - 100)
            end = min(len(content), idx + 300)
            excerpt = content[start:end]
        else:
            excerpt = content[:300]

        results.append({
            "id": doc.id,
            "filename": doc.filename,
            "excerpt": excerpt,
        })

    return results
