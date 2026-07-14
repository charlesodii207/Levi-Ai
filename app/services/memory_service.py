from sqlalchemy.orm import Session
from app.models.memory import Memory
from app.services.ai_service import generate_response


def get_user_memories(user_id: int, db: Session) -> list[dict]:
    """Fetch all memories for a user."""
    memories = db.query(Memory).filter(Memory.user_id == user_id).all()
    return [{"key": m.key, "value": m.value} for m in memories]


def format_memories_for_prompt(memories: list[dict]) -> str:
    """Format memories into a string to inject into the system prompt."""
    if not memories:
        return ""
    lines = "\n".join([f"- {m['key']}: {m['value']}" for m in memories])
    return f"\n\nWhat you know about this user:\n{lines}\n"


def save_memory(user_id: int, key: str, value: str, db: Session):
    """Save or update a memory for a user."""
    existing = db.query(Memory).filter(
        Memory.user_id == user_id,
        Memory.key == key
    ).first()

    if existing:
        existing.value = value
    else:
        memory = Memory(user_id=user_id, key=key, value=value)
        db.add(memory)

    db.commit()


def extract_and_save_memories(
    user_id: int,
    user_message: str,
    ai_response: str,
    db: Session
):
    """
    After each conversation turn, silently extract key facts
    about the user and save them as memories.
    """
    prompt = f"""Analyze this conversation and extract any personal facts about the USER ONLY.
Look for: name, age, location, job, hobbies, preferences, goals, projects, family, health, habits.

User said: "{user_message}"
Assistant replied: "{ai_response}"

If you find personal facts about the user, respond with a JSON array like this:
[{{"key": "name", "value": "Charles"}}, {{"key": "favourite food", "value": "rice"}}]

If no personal facts are found, respond with exactly: []

Only extract FACTS about the user. Do not extract general information or opinions.
Respond with ONLY the JSON array, nothing else."""

    try:
        result = generate_response(prompt, [])
        result = result.strip()

        # Extract JSON from response
        import re
        import json
        match = re.search(r'\[.*\]', result, re.DOTALL)
        if not match:
            return

        facts = json.loads(match.group())
        for fact in facts:
            if isinstance(fact, dict) and "key" in fact and "value" in fact:
                save_memory(user_id, fact["key"].lower(), fact["value"], db)
    except Exception:
        pass  # Memory extraction is silent — never break the chat
