"""
rag_service.py

Retrieval-Augmented Generation (RAG) service for Levi AI's Knowledge Base.

This module sits between the chat endpoint and the Groq AI engine. Before a
user's message is sent to the model, it retrieves the most relevant chunks
from their Knowledge Base and injects them into the system prompt.

Design notes:
- Retrieval backend is pluggable. `KeywordRetriever` (below) works today with
  zero new infra, on top of the existing `KnowledgeBase.content` column.
  `EmbeddingRetriever` is stubbed for a future pgvector-based upgrade — the
  call site (`get_context_for_query`) never has to change.
- Documents are chunked at query time so long files don't get dropped
  wholesale into the prompt — only the relevant slice does.
- A token/character budget keeps injected context from crowding out the
  actual conversation history sent to Groq.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Protocol

from sqlalchemy.orm import Session
from sqlalchemy import or_

from app.models.knowledge_base import KnowledgeBase

logger = logging.getLogger("rag_service")

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

MAX_CONTEXT_CHARS = 6000       # total budget for injected KB context
CHUNK_SIZE = 800               # characters per chunk when splitting a doc
CHUNK_OVERLAP = 150            # overlap between adjacent chunks
TOP_K_DOCS = 5                 # how many documents to pull candidates from
TOP_K_CHUNKS = 4               # how many chunks to actually inject


@dataclass
class RetrievedChunk:
    doc_id: int
    filename: str
    text: str
    score: float  # higher is better; meaning depends on retriever


# ---------------------------------------------------------------------------
# Retriever interface — swap KeywordRetriever for EmbeddingRetriever later
# without touching anything downstream.
# ---------------------------------------------------------------------------

class Retriever(Protocol):
    def retrieve(
        self, db: Session, user_id: int, query: str, top_k: int = TOP_K_CHUNKS
    ) -> list[RetrievedChunk]:
        ...


def _chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """Split text into overlapping chunks so long documents can be scored
    and retrieved at the paragraph/section level instead of all-or-nothing."""
    if not text:
        return []

    chunks: list[str] = []
    start = 0
    length = len(text)
    while start < length:
        end = min(start + chunk_size, length)
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end == length:
            break
        start = end - overlap
    return chunks


def _keyword_score(chunk: str, terms: list[str]) -> float:
    """Simple term-frequency scoring. Case-insensitive. Rewards chunks that
    contain more distinct query terms and more occurrences of each."""
    if not terms:
        return 0.0
    lowered = chunk.lower()
    score = 0.0
    for term in terms:
        count = lowered.count(term)
        if count:
            # log-ish dampening so one repeated word can't dominate
            score += 1 + min(count - 1, 3) * 0.25
    return score


class KeywordRetriever:
    """Retrieval using the existing KnowledgeBase.content column. No new
    infrastructure required — this is the retriever Levi AI ships with today."""

    def retrieve(
        self, db: Session, user_id: int, query: str, top_k: int = TOP_K_CHUNKS
    ) -> list[RetrievedChunk]:
        terms = [t for t in re.findall(r"\w+", query.lower()) if len(t) > 2]
        if not terms:
            return []

        # Narrow to candidate documents first (DB-level filter), then score
        # chunks in Python. Keeps the SQL simple and portable.
        filters = [KnowledgeBase.content.ilike(f"%{t}%") for t in terms]
        candidates = (
            db.query(KnowledgeBase)
            .filter(KnowledgeBase.user_id == user_id, or_(*filters))
            .order_by(KnowledgeBase.created_at.desc())
            .limit(TOP_K_DOCS)
            .all()
        )

        scored: list[RetrievedChunk] = []
        for doc in candidates:
            for chunk in _chunk_text(doc.content or ""):
                score = _keyword_score(chunk, terms)
                if score > 0:
                    scored.append(
                        RetrievedChunk(
                            doc_id=doc.id,
                            filename=doc.filename,
                            text=chunk,
                            score=score,
                        )
                    )

        scored.sort(key=lambda c: c.score, reverse=True)
        return scored[:top_k]


class EmbeddingRetriever:
    """Placeholder for a future pgvector-backed retriever. Same interface as
    KeywordRetriever, so swapping it in is a one-line change at the bottom
    of this file — nothing in the chat endpoint needs to change.

    To implement later:
      1. Add a `KnowledgeBaseChunk` table: (id, doc_id, chunk_text, embedding vector(1536))
      2. On upload, chunk the doc and store an embedding per chunk
      3. Here: embed `query`, run a pgvector `<=>` similarity query, return top_k
    """

    def retrieve(
        self, db: Session, user_id: int, query: str, top_k: int = TOP_K_CHUNKS
    ) -> list[RetrievedChunk]:
        raise NotImplementedError(
            "EmbeddingRetriever not yet implemented — see class docstring."
        )


# Active retriever. Change this one line when you're ready to move to embeddings.
_retriever: Retriever = KeywordRetriever()


# ---------------------------------------------------------------------------
# Public API used by the chat endpoint
# ---------------------------------------------------------------------------

def get_context_for_query(db: Session, user_id: int, query: str) -> str | None:
    """Retrieve and format KB context for a user's chat message.

    Returns None if nothing relevant was found (caller should skip
    augmentation entirely rather than inject an empty block).
    """
    try:
        chunks = _retriever.retrieve(db, user_id, query, top_k=TOP_K_CHUNKS)
    except NotImplementedError:
        raise
    except Exception:
        logger.exception("KB retrieval failed for user_id=%s", user_id)
        return None

    if not chunks:
        return None

    parts: list[str] = []
    used_chars = 0
    for chunk in chunks:
        piece = f"[From: {chunk.filename}]\n{chunk.text}"
        if used_chars + len(piece) > MAX_CONTEXT_CHARS:
            break
        parts.append(piece)
        used_chars += len(piece)

    if not parts:
        return None

    return "\n\n---\n\n".join(parts)


def build_augmented_system_prompt(base_system_prompt: str, kb_context: str | None) -> str:
    """Combine the assistant's normal system prompt with retrieved KB
    context, if any was found. Keeps the instruction explicit so the model
    doesn't hallucinate beyond what was actually retrieved."""
    if not kb_context:
        return base_system_prompt

    return (
        f"{base_system_prompt}\n\n"
        "You have been given relevant excerpts from the user's uploaded "
        "documents below. Use them to answer if relevant. If the excerpts "
        "don't contain the answer, say so rather than guessing.\n\n"
        f"--- Knowledge Base Context ---\n{kb_context}\n--- End Context ---"
    )
