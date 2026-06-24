from sqlalchemy.orm import Session

from app.models.conversation import Conversation


def create_conversation(db: Session, user_id: int, title: str = "New Chat"):
    conversation = Conversation(
        user_id=user_id,
        title=title
    )

    db.add(conversation)
    db.commit()
    db.refresh(conversation)

    return conversation


def get_user_conversations(db: Session, user_id: int):
    return (
        db.query(Conversation)
        .filter(Conversation.user_id == user_id)
        .order_by(Conversation.updated_at.desc())
        .all()
    )


def get_conversation(db: Session, conversation_id: int, user_id: int):
    return (
        db.query(Conversation)
        .filter(
            Conversation.id == conversation_id,
            Conversation.user_id == user_id
        )
        .first()
    )


def rename_conversation(
    db: Session,
    conversation: Conversation,
    title: str
):
    conversation.title = title

    db.commit()
    db.refresh(conversation)

    return conversation


def delete_conversation(
    db: Session,
    conversation: Conversation
):
    db.delete(conversation)
    db.commit()