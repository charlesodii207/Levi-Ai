from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.models.memory import Memory
from app.services.memory_service import save_memory

router = APIRouter(prefix="/memory", tags=["Memory"])


class MemoryOut(BaseModel):
    id: int
    key: str
    value: str

    class Config:
        from_attributes = True


class MemoryUpdate(BaseModel):
    key: str
    value: str


@router.get("/", response_model=list[MemoryOut])
def get_memories(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get all memories for the current user."""
    memories = db.query(Memory).filter(
        Memory.user_id == current_user.id
    ).all()
    return memories


@router.delete("/{memory_id}")
def delete_memory(
    memory_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a specific memory."""
    memory = db.query(Memory).filter(
        Memory.id == memory_id,
        Memory.user_id == current_user.id
    ).first()

    if not memory:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Memory not found")

    db.delete(memory)
    db.commit()
    return {"message": "Memory deleted"}


@router.delete("/")
def delete_all_memories(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete ALL memories for the current user."""
    memories = db.query(Memory).filter(
        Memory.user_id == current_user.id
    ).all()
    for m in memories:
        db.delete(m)
    db.commit()
    return {"message": f"Deleted {len(memories)} memories"}


@router.patch("/{memory_id}")
def update_memory(
    memory_id: int,
    body: MemoryUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update a specific memory."""
    memory = db.query(Memory).filter(
        Memory.id == memory_id,
        Memory.user_id == current_user.id
    ).first()

    if not memory:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Memory not found")

    memory.key = body.key
    memory.value = body.value
    db.commit()
    return {"message": "Memory updated"}
