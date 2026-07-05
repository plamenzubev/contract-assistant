from django.contrib import admin

from .models import Chunk, Document


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ("id", "original_filename", "file_type", "page_count", "char_count", "uploaded_at")
    list_filter = ("file_type",)
    search_fields = ("original_filename", "extracted_text")
    readonly_fields = ("extracted_text", "char_count", "page_count", "uploaded_at")


@admin.register(Chunk)
class ChunkAdmin(admin.ModelAdmin):
    list_display = ("id", "document", "index", "content_preview")
    list_filter = ("document",)
    search_fields = ("content",)
    # Show the content, but NOT the raw 768-dimensional vector (unreadable).
    readonly_fields = ("document", "index", "content", "embedding_preview")
    exclude = ("embedding",)

    @admin.display(description="content")
    def content_preview(self, obj):
        text = obj.content[:120].replace("\n", " ")
        return f"{text}…" if len(obj.content) > 120 else text

    @admin.display(description="embedding (first 8 dims)")
    def embedding_preview(self, obj):
        # Just the first few numbers + the dimensionality — enough to see it's there.
        head = ", ".join(f"{x:.4f}" for x in obj.embedding[:8])
        return f"dim={len(obj.embedding)} → [{head}, …]"
