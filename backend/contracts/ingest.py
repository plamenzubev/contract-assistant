"""Chunking + embedding of a document. Shared by the upload view and the CLI command."""
from .chunking import split_text
from .embeddings import embed_text
from .models import Chunk


def ingest_document(document, chunk_size: int = 800, overlap: int = 150) -> int:
    """Chunks the document, computes embeddings, and saves the chunks. Returns the chunk count.
    Deletes the old chunks first so it's safe to run repeatedly."""
    pieces = split_text(document.extracted_text, chunk_size=chunk_size, overlap=overlap)
    document.chunks.all().delete()

    chunks = [
        Chunk(document=document, index=i, content=content, embedding=embed_text(content))
        for i, content in enumerate(pieces)
    ]
    Chunk.objects.bulk_create(chunks)
    return len(chunks)
