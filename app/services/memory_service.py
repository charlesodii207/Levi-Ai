from sqlalchemy.orm import Session

from app.models.memory import Memory


class MemoryService:

    @staticmethod
    def save_memory(
        db: Session,
        user_id: int,
        key: str,
        value: str
    ):
        """
        Save a memory.
        If the key already exists, update it.
        """

        memory = (
            db.query(Memory)
            .filter(
                Memory.user_id == user_id,
                Memory.key == key
            )
            .first()
        )

        if memory:
            memory.value = value
        else:
            memory = Memory(
                user_id=user_id,
                key=key,
                value=value
            )
            db.add(memory)

        db.commit()
        db.refresh(memory)

        return memory

    @staticmethod
    def get_memories(
        db: Session,
        user_id: int
    ):
        """
        Get all memories belonging to a user.
        """

        memories = (
            db.query(Memory)
            .filter(Memory.user_id == user_id)
            .all()
        )

        return memories

    @staticmethod
    def get_memory(
        db: Session,
        user_id: int,
        key: str
    ):
        """
        Get one specific memory by key.
        """

        memory = (
            db.query(Memory)
            .filter(
                Memory.user_id == user_id,
                Memory.key == key
            )
            .first()
        )

        return memory

    @staticmethod
    def delete_memory(
        db: Session,
        user_id: int,
        key: str
    ):
        """
        Delete a memory.
        """

        memory = (
            db.query(Memory)
            .filter(
                Memory.user_id == user_id,
                Memory.key == key
            )
            .first()
        )

        if memory:
            db.delete(memory)
            db.commit()

        return True