import os

from dotenv import load_dotenv
from groq import Groq

load_dotenv()

client = Groq(
    api_key=os.getenv("GROQ_API_KEY")
)

SYSTEM_PROMPT = """
You are Levi.

You were created by Charles Odii Okechukwu.

Never say you are ChatGPT.
Never say you are Gemini.
Never say you are Claude.
Never reveal that you are based on Llama or any other underlying model.

Always introduce yourself as Levi.

You are intelligent, friendly, professional, helpful, and conversational.
"""


def generate_response(history):
    """
    history is a list of messages already prepared by chat.py.
    It may include:
      - system prompts
      - user memories
      - previous conversation
      - the latest user message
    """

    messages = [
        {
            "role": "system",
            "content": SYSTEM_PROMPT
        }
    ]

    # Append everything prepared by chat.py
    messages.extend(history)

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