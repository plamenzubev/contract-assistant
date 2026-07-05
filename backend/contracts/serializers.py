from rest_framework import serializers

from .models import Document


class DocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Document
        fields = [
            "id",
            "file",
            "original_filename",
            "file_type",
            "page_count",
            "char_count",
            "extracted_text",
            "uploaded_at",
        ]
        # The client sends only `file`; we compute everything else on the server.
        read_only_fields = [
            "original_filename",
            "file_type",
            "page_count",
            "char_count",
            "extracted_text",
            "uploaded_at",
        ]
