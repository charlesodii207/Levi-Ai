import os
from typing import Generator, Optional

from dotenv import load_dotenv
from groq import Groq
import google.generativeai as genai

load_dotenv()

groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

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

WHEN ASKED WHO YOU ARE
Reply naturally, for example:
"Hello! I'm Levi, your intelligent AI assistant created by Charles Odii Okechukwu. I'm here to help you with coding, learning, business, productivity, research, and much more."

WHEN ASKED WHO CREATED YOU
Reply: "I was created by Charles Odii Okechukwu."

Always stay in character as Levi.
"""

# Appended only for Gemini/Nova calls. This is what actually makes Nova
# "better" — not a longer token limit alone, but an instruction to reason
# more carefully before answering. Keeps the base SYSTEM_PROMPT identical
# for both models so Levi's core identity/personality never diverges.
NOVA_ANALYTICAL_ADDENDUM = """

ENHANCED ANALYTICAL MODE (Nova)
You are currently running as Levi Nova, the more capable analytical mode. When responding:
- Think through the problem carefully before answering — consider multiple angles, edge cases, or interpretations before settling on your response.
- For any analysis, comparison, or recommendation: back it up with specific reasoning, not just a conclusion. Explain the "why," not just the "what."
- If data, numbers, or trends are involved, reason through them explicitly rather than pattern-matching to a plausible-sounding answer.
- Where relevant, note important caveats, risks, or alternative interpretations a careful expert would flag — don't oversimplify complex topics.
- Prioritize accuracy and depth over speed. Take the space needed to give a genuinely thorough answer rather than a surface-level one.
- This applies to all tasks, not just numerical analysis — writing, research, business strategy, and code should all reflect the same level of careful, expert-level thinking.
"""

# Maps the user-facing model name to which provider actually handles it.
# "swift" -> Groq (Llama), "nova" -> Gemini. Add "sonnet"/"opus" here later
# when Claude replaces Groq at launch — nothing else in this file needs to
# change, just this map and a new _call_claude* set of functions.
MODEL_PROVIDERS = {
    "swift": "groq",
    "nova": "gemini",
}

GROQ_MODEL = "llama-3.3-70b-versatile"
GEMINI_MODEL = "gemini-flash-latest"

DEFAULT_MODEL = "swift"


def _resolve_provider(model: Optional[str]) -> str:
    key = (model or DEFAULT_MODEL).lower()
    provider = MODEL_PROVIDERS.get(key)
    if not provider:
        print(f"[Levi] Unknown model '{model}', falling back to '{DEFAULT_MODEL}'")
        provider = MODEL_PROVIDERS[DEFAULT_MODEL]
    return provider


def build_messages(prompt: str, history: list[dict] = None) -> list[dict]:
    """Build the full messages list with system prompt + history + new message.
    Used for Groq (OpenAI-style role format: system/user/assistant)."""
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    if history:
        for msg in history:
            messages.append({
                "role": msg["role"],
                "content": msg["content"]
            })

    messages.append({"role": "user", "content": prompt})
    return messages


def _build_gemini_history(history: list[dict] = None) -> list[dict]:
    """Gemini uses a different role format than Groq/OpenAI: 'model' instead
    of 'assistant', and history is passed separately from the system prompt
    rather than as a system-role message."""
    gemini_history = []
    if history:
        for msg in history:
            # Gemini has no "system" role in chat history — memory/KB context
            # messages get folded in as a user turn instead so they're not lost.
            role = "model" if msg["role"] == "assistant" else "user"
            gemini_history.append({"role": role, "parts": [msg["content"]]})
    return gemini_history


# ── Groq (Levi Swift) ───────────────────────────────────────────────────────

def _generate_groq(prompt: str, history: list[dict] = None) -> str:
    messages = build_messages(prompt, history)
    try:
        response = groq_client.chat.completions.create(
            model=GROQ_MODEL,
            messages=messages,
            temperature=0.7,
            max_tokens=1024,
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"[Levi] Groq error: {e}")
        return "I'm temporarily unavailable. Please try again in a moment."


def _generate_groq_stream(prompt: str, history: list[dict] = None) -> Generator[str, None, None]:
    messages = build_messages(prompt, history)
    try:
        stream = groq_client.chat.completions.create(
            model=GROQ_MODEL,
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
        print(f"[Levi] Groq stream error: {e}")
        yield "I'm temporarily unavailable. Please try again in a moment."


# ── Gemini (Levi Nova) ──────────────────────────────────────────────────────

def _generate_gemini(prompt: str, history: list[dict] = None) -> str:
    try:
        model = genai.GenerativeModel(
            model_name=GEMINI_MODEL,
            system_instruction=SYSTEM_PROMPT + NOVA_ANALYTICAL_ADDENDUM,
        )
        chat = model.start_chat(history=_build_gemini_history(history))
        response = chat.send_message(
            prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=0.7,
                max_output_tokens=4096,
            ),
        )
        return response.text
    except Exception as e:
        print(f"[Levi] Gemini error: {e}")
        return "I'm temporarily unavailable. Please try again in a moment."


def _generate_gemini_stream(prompt: str, history: list[dict] = None) -> Generator[str, None, None]:
    try:
        model = genai.GenerativeModel(
            model_name=GEMINI_MODEL,
            system_instruction=SYSTEM_PROMPT + NOVA_ANALYTICAL_ADDENDUM,
        )
        chat = model.start_chat(history=_build_gemini_history(history))
        response = chat.send_message(
            prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=0.7,
                max_output_tokens=4096,
            ),
            stream=True,
        )
        for chunk in response:
            if chunk.text:
                yield chunk.text
    except Exception as e:
        print(f"[Levi] Gemini stream error: {e}")
        yield "I'm temporarily unavailable. Please try again in a moment."


# ── Public API — used by chat.py, unchanged call shape plus a `model` arg ──

def generate_response(prompt: str, history: list[dict] = None, model: Optional[str] = None) -> str:
    """Generate a full response with conversation history context.
    `model` is the user-facing name: "swift" (Groq/Llama) or "nova" (Gemini)."""
    provider = _resolve_provider(model)
    if provider == "gemini":
        return _generate_gemini(prompt, history)
    return _generate_groq(prompt, history)


def generate_response_stream(
    prompt: str, history: list[dict] = None, model: Optional[str] = None
) -> Generator[str, None, None]:
    """Stream a response token by token with conversation history context."""
    provider = _resolve_provider(model)
    if provider == "gemini":
        yield from _generate_gemini_stream(prompt, history)
    else:
        yield from _generate_groq_stream(prompt, history)


def generate_title(first_message: str) -> str:
    """Auto-generate a short conversation title from the first user message.
    Always uses Groq regardless of chat model — titles are trivial and this
    keeps title generation fast and free even for Nova/paid conversations."""
    try:
        response = groq_client.chat.completions.create(
            model=GROQ_MODEL,
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