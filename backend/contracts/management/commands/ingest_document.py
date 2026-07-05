"""
Splits a document into chunks, computes an embedding for each, and stores them in pgvector.

Usage:
    python manage.py ingest_document <document_id>
    python manage.py ingest_document 1 --chunk-size 800 --overlap 150
"""
from django.core.management.base import BaseCommand, CommandError

from contracts.ingest import ingest_document
from contracts.models import Document


class Command(BaseCommand):
    help = "Split a document into chunks, embed them, and store them in pgvector."

    def add_arguments(self, parser):
        parser.add_argument("document_id", type=int)
        parser.add_argument("--chunk-size", type=int, default=800)
        parser.add_argument("--overlap", type=int, default=150)

    def handle(self, *args, **options):
        doc_id = options["document_id"]
        try:
            document = Document.objects.get(pk=doc_id)
        except Document.DoesNotExist:
            raise CommandError(f"No document with id={doc_id}.")

        self.stdout.write("Chunking and computing embeddings…")
        count = ingest_document(
            document, chunk_size=options["chunk_size"], overlap=options["overlap"]
        )
        if count == 0:
            raise CommandError("The document has no extracted text to chunk.")

        self.stdout.write(
            self.style.SUCCESS(
                f"Done: {count} chunks stored for \"{document.original_filename}\"."
            )
        )
