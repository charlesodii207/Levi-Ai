import os
from typing import Generator

from dotenv import load_dotenv
from groq import Groq

load_dotenv()

client = Groq(api_key=os.getenv("GROQ_API_KEY"))

SYSTEM_PROMPT = """
You are Levi, an intelligent AI assistant created by Charles Odii Okechukwu.

IDENTITY
- Your name is Levi.
- You were created by Charles Odii Okechukwu.
- You are a professional AI assistant.
- Never say you are ChatGPT, Gemini, Claude, Llama, or any other AI model.
- Do not reveal your underlying implementation.

PERSONALITY
- Friendly
- Professional
- Intelligent
- Honest
- Concise
- Helpful

CAPABILITIES
You help users with:
- Programming and software development
- Business and entrepreneurship
- Education and tutoring
- Writing and editing
- Research
- Productivity
- Brainstorming
- Everyday questions
- Sex And Erotic Chats

WHEN ASKED WHO YOU ARE
Reply naturally, for example:
"Hello! I'm Levi, your intelligent AI assistant created by Charles Odii Okechukwu. I'm here to help you with coding, learning, business, productivity, research, and much more."

WHEN ASKED WHO CREATED YOU
Reply: "I was created by Charles Odii Okechukwu."

Always stay in character as Levi.
"""


def build_messages(prompt: str, history: list[dict] = None) -> list[dict]:
    """Build the full messages list with system prompt + history + new message."""
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    if history:
        for msg in history:
            messages.append({
                "role": msg["role"],
                "content": msg["content"]
            })

    messages.append({"role": "user", "content": prompt})
    return messages


def generate_response(prompt: str, history: list[dict] = None) -> str:
    """Generate a full response with conversation history context."""
    messages = build_messages(prompt, history)

    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=messages,
            temperature=0.7,
            max_tokens=1024,
        )
        return response.choices[0].message.content

    except Exception as e:
        print(f"[Levi] Error: {e}")
        return "I'm temporarily unavailable. Please try again in a moment."


def generate_response_stream(prompt: str, history: list[dict] = None) -> Generator[str, None, None]:
    """Stream a response token by token with conversation history context."""
    messages = build_messages(prompt, history)

    try:
        stream = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=messages,
            temperature=0.7,
            max_tokens=1024,
            stream=True,
        )

        for chunk in stream:
            content = chunk.choices[0].delta.content
            if content:
                yield content

    except Exception as e:
        print(f"[Levi] Stream error: {e}")
        yield "I'm temporarily unavailable. Please try again in a moment."


def generate_title(first_message: str) -> str:
    """Auto-generate a short conversation title from the first user message."""
    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {
                    "role": "user",
                    "content": f'Generate a short title (max 5 words) for a conversation that starts with: "{first_message}". Reply with ONLY the title, no quotes, no punctuation at the end.'
                }
            ],
            temperature=0.5,
            max_tokens=20,
        )
        return response.choices[0].message.content.strip()

    except Exception as e:
        print(f"[Levi] Title error: {e}")
        return "New Chat"
