from django.db import models
from pgvector.django import VectorField


def contract_upload_path(instance, filename):
    # Files go to MEDIA_ROOT/contracts/<name>. Django appends a suffix on collision.
    return f"contracts/{filename}"


class Document(models.Model):
    """A single uploaded contract: the original file + the text extracted from it."""

    class FileType(models.TextChoices):
        PDF = "pdf", "PDF"
        DOCX = "docx", "DOCX"

    file = models.FileField(upload_to=contract_upload_path)
    original_filename = models.CharField(max_length=255)
    file_type = models.CharField(max_length=10, choices=FileType.choices)

    # The raw material for Stage 2 (chunking + embeddings).
    extracted_text = models.TextField(blank=True)

    # Metadata useful for citations and quick previews.
    page_count = models.PositiveIntegerField(default=0)
    char_count = models.PositiveIntegerField(default=0)

    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-uploaded_at"]

    def __str__(self):
        return f"{self.original_filename} ({self.file_type}, {self.char_count} chars)"


class Chunk(models.Model):
    """
    A single chunk of a contract + its embedding.
    `index` preserves the chunk's order within the document (useful for citations in Stage 4).
    `embedding` is a 768-dimensional vector (nomic-embed-text) — this is the "meaning" of
    the chunk, over which pgvector runs its nearest-neighbor search in Stage 3.
    """

    document = models.ForeignKey(
        Document, related_name="chunks", on_delete=models.CASCADE
    )
    index = models.PositiveIntegerField()
    content = models.TextField()
    embedding = VectorField(dimensions=768)

    class Meta:
        ordering = ["document_id", "index"]
        # One chunk per position in a document — protects us from duplicates on re-runs.
        constraints = [
            models.UniqueConstraint(
                fields=["document", "index"], name="unique_chunk_per_document"
            )
        ]

    def __str__(self):
        preview = self.content[:50].replace("\n", " ")
        return f"{self.document_id}#{self.index}: {preview}…"
