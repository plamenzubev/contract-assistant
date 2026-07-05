"""
The RAG logic: retrieval → prompt assembly → calling the local LLM.

The flow:
  1. retrieve()      — finds the nearest chunks for the question (pgvector).
  2. build_messages()— joins them into numbered context + a system prompt with the rules.
  3. chat()          — sends the messages to Ollama and returns the answer text.
  4. answer_question()— orchestrates the three above and returns answer + sources.
"""
import json

import httpx
from django.conf import settings
from pgvector.django import CosineDistance

from .embeddings import embed_text
from .models import Chunk

# The system prompt is the heart of RAG: here we enforce "context only + citations".
SYSTEM_PROMPT = """You are a contract analysis assistant. Answer the user's \
question using ONLY the numbered context passages provided below. Follow these \
rules strictly:
- Use only information from the context. Do not use outside knowledge or assumptions.
- If the answer is not in the context, say exactly: "I couldn't find this in the document."
- After each claim, cite the passage number(s) you used, e.g. [1] or [2][3].
- Be concise and quote key figures (dates, amounts, durations) exactly as written.
- Answer in the same language as the question."""


def retrieve(document_id, question: str, k: int = 5) -> list[Chunk]:
    """The nearest k chunks for the question, each annotated with .distance."""
    query_embedding = embed_text(question)
    return list(
        Chunk.objects.filter(document_id=document_id)
        .annotate(distance=CosineDistance("embedding", query_embedding))
        .order_by("distance")[:k]
    )


def build_messages(question: str, chunks: list[Chunk]) -> list[dict]:
    """Assembles the chat messages: system (rules + context) and user (the question)."""
    context = "\n\n".join(f"[{i + 1}] {c.content}" for i, c in enumerate(chunks))
    system = f"{SYSTEM_PROMPT}\n\nContext passages:\n{context}"
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": question},
    ]


def chat(messages: list[dict]) -> str:
    """Sends the messages to Ollama (no streaming — that comes in Stage 5)."""
    response = httpx.post(
        f"{settings.OLLAMA_BASE_URL}/api/chat",
        json={
            "model": settings.OLLAMA_CHAT_MODEL,
            "messages": messages,
            "stream": False,
        },
        timeout=180.0,  # generating with an 8B model on CPU can take a while
    )
    response.raise_for_status()
    return response.json()["message"]["content"]


def _sources(chunks: list[Chunk]) -> list[dict]:
    """The sources for the answer. "ref" = the number [1],[2]… in the prompt;
    "index" = the real chunk.index in the document (for the clickable citations)."""
    return [
        {
            "ref": i + 1,
            "index": c.index,
            "distance": round(c.distance, 4),
            "content": c.content,
        }
        for i, c in enumerate(chunks)
    ]


def prepare(document_id, question: str, k: int = 5) -> tuple[list[dict], list[dict]]:
    """Retrieval + prompt assembly. Returns (messages, sources) — without calling the LLM.
    Shared by the synchronous and the streaming paths."""
    chunks = retrieve(document_id, question, k)
    return build_messages(question, chunks), _sources(chunks)


def stream_chat(messages: list[dict]):
    """Generator: yields the answer tokens one by one (Ollama stream=True)."""
    with httpx.stream(
        "POST",
        f"{settings.OLLAMA_BASE_URL}/api/chat",
        json={"model": settings.OLLAMA_CHAT_MODEL, "messages": messages, "stream": True},
        timeout=None,  # a long stream shouldn't time out
    ) as response:
        response.raise_for_status()
        # Ollama returns one JSON object per line.
        for line in response.iter_lines():
            if not line:
                continue
            data = json.loads(line)
            token = data.get("message", {}).get("content", "")
            if token:
                yield token
            if data.get("done"):
                return


def answer_question(
    document_id, question: str, k: int = 5, include_prompt: bool = False
) -> dict:
    """The full RAG flow (no streaming). Returns the answer + the sources."""
    messages, sources = prepare(document_id, question, k)
    answer = chat(messages)

    result = {"answer": answer, "sources": sources}
    if include_prompt:
        # For learning: we also return the exact system prompt that went to the model.
        result["system_prompt"] = messages[0]["content"]
    return result
