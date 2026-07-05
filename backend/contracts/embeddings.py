"""Computing embeddings via the local Ollama server."""
import httpx
from django.conf import settings


def embed_text(text: str) -> list[float]:
    """
    Returns an embedding vector for the given text using Ollama.
    The same model is used both at upload (the chunks) and at query time (the question) —
    otherwise the vectors aren't in the same space and proximity is meaningless.
    """
    response = httpx.post(
        f"{settings.OLLAMA_BASE_URL}/api/embeddings",
        json={"model": settings.OLLAMA_EMBED_MODEL, "prompt": text},
        # The first call after Ollama starts loads the model into memory → slow.
        timeout=120.0,
    )
    response.raise_for_status()
    return response.json()["embedding"]
