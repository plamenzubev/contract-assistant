import io
import json
import os

import httpx
from django.conf import settings
from django.core.files.base import ContentFile
from django.db import connection
from django.http import JsonResponse, StreamingHttpResponse
from django.views.decorators.csrf import csrf_exempt
from rest_framework import viewsets
from rest_framework.decorators import api_view
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response

from .ingest import ingest_document
from .models import Document
from .parsing import extract_text
from .rag import answer_question, prepare, retrieve, stream_chat
from .serializers import DocumentSerializer

# Upload size limit (full error handling comes in Stage 6).
MAX_UPLOAD_SIZE = 10 * 1024 * 1024  # 10 MB
SUPPORTED_TYPES = {"pdf", "docx"}


def _ollama_error(exc) -> str:
    """A friendly message when Ollama has a problem (instead of a raw traceback)."""
    return (
        f"The LLM service (Ollama) is not responding: {exc}. "
        f"Check that Ollama is running ('ollama serve' or 'brew services start ollama') "
        f"and that the models are downloaded ('ollama pull llama3.1:8b' and 'nomic-embed-text')."
    )


@api_view(["GET"])
def health(request):
    """Health check for Stage 0: Django + database + pgvector availability."""
    db_ok = False
    pgvector_available = False
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1;")
            db_ok = cursor.fetchone() == (1,)
            cursor.execute(
                "SELECT 1 FROM pg_available_extensions WHERE name = 'vector';"
            )
            pgvector_available = cursor.fetchone() is not None
    except Exception as exc:  # pragma: no cover
        return Response({"status": "error", "detail": str(exc)}, status=500)

    # Also check whether Ollama is reachable and which models are available.
    ollama = {"reachable": False, "models": []}
    try:
        tags = httpx.get(f"{settings.OLLAMA_BASE_URL}/api/tags", timeout=3.0).json()
        ollama["reachable"] = True
        ollama["models"] = [m["name"] for m in tags.get("models", [])]
    except Exception:
        pass

    return Response(
        {
            "status": "ok",
            "database": db_ok,
            "pgvector_available_in_image": pgvector_available,
            "ollama": ollama,
        }
    )


class DocumentViewSet(viewsets.ModelViewSet):
    """
    CRUD for contracts.
      POST   /api/documents/       -> upload + text extraction
      GET    /api/documents/       -> list
      GET    /api/documents/{id}/  -> a single document (with the full extracted text)
      DELETE /api/documents/{id}/  -> delete
    """

    queryset = Document.objects.all()
    serializer_class = DocumentSerializer
    parser_classes = [MultiPartParser, FormParser]

    def create(self, request, *args, **kwargs):
        upload = request.FILES.get("file")
        if upload is None:
            return Response(
                {"detail": "No file provided. Send it in the multipart field 'file'."},
                status=400,
            )

        if upload.size > MAX_UPLOAD_SIZE:
            return Response(
                {"detail": f"File is too large (max {MAX_UPLOAD_SIZE // (1024*1024)} MB)."},
                status=400,
            )

        # Determine the type from the file extension.
        ext = os.path.splitext(upload.name)[1].lower().lstrip(".")
        if ext not in SUPPORTED_TYPES:
            return Response(
                {"detail": f"Unsupported type '.{ext}'. Accepted: {', '.join(SUPPORTED_TYPES)}."},
                status=400,
            )

        # Read the bytes once: once for extraction, once for saving the file.
        # (This way we don't fight the stream position after the parser has read it.)
        raw = upload.read()
        try:
            text, page_count = extract_text(io.BytesIO(raw), ext)
        except Exception as exc:
            return Response(
                {"detail": f"Failed to parse the file: {exc}"},
                status=422,
            )

        if not text:
            return Response(
                {
                    "detail": (
                        "No text found. The file may be scanned (an image), "
                        "which would require OCR — out of scope for now."
                    )
                },
                status=422,
            )

        doc = Document.objects.create(
            file=ContentFile(raw, name=upload.name),
            original_filename=upload.name,
            file_type=ext,
            extracted_text=text,
            page_count=page_count,
            char_count=len(text),
        )

        # Chunk + embed right away so it's ready to query (requires Ollama).
        # If Ollama isn't running, the document is still saved — the chunks can be built later
        # with `python manage.py ingest_document <id>`. (Stage 6: make it a background task.)
        try:
            chunk_count = ingest_document(doc)
            warning = None
        except Exception as exc:
            chunk_count = 0
            warning = f"The document was uploaded, but chunking failed: {exc}"

        data = self.get_serializer(doc).data
        data["chunk_count"] = chunk_count
        if warning:
            data["warning"] = warning
        return Response(data, status=201)


@api_view(["POST"])
def search(request):
    """
    Vector search WITHOUT the LLM (Stage 3).
    Body: {"document_id": 1, "question": "when do I pay?", "k": 5}
    Returns the nearest chunks + their cosine distance (0 = closest).
    """
    document_id = request.data.get("document_id")
    question = (request.data.get("question") or "").strip()
    k = int(request.data.get("k", 5))

    if not document_id or not question:
        return Response(
            {"detail": "Both 'document_id' and 'question' are required."}, status=400
        )
    if not Document.objects.filter(pk=document_id).exists():
        return Response({"detail": f"No document with id={document_id}."}, status=404)

    # The vector search lives in rag.retrieve (shared with /api/ask/).
    try:
        results = retrieve(document_id, question, k)
    except httpx.HTTPError as exc:
        return Response({"detail": _ollama_error(exc)}, status=503)

    return Response(
        {
            "document_id": int(document_id),
            "question": question,
            "results": [
                {
                    "index": c.index,
                    "distance": round(c.distance, 4),
                    "content": c.content,
                }
                for c in results
            ],
        }
    )


@api_view(["POST"])
def ask(request):
    """
    Full RAG answer with citations (Stage 4).
    Body: {"document_id": 1, "question": "...", "k": 5, "include_prompt": true}
    Returns {"answer": "...", "sources": [...]} — sources maps the citations [1],[2]...
    """
    document_id = request.data.get("document_id")
    question = (request.data.get("question") or "").strip()
    k = int(request.data.get("k", 5))
    include_prompt = bool(request.data.get("include_prompt", False))

    if not document_id or not question:
        return Response(
            {"detail": "Both 'document_id' and 'question' are required."}, status=400
        )
    if not Document.objects.filter(pk=document_id).exists():
        return Response({"detail": f"No document with id={document_id}."}, status=404)

    try:
        result = answer_question(document_id, question, k, include_prompt=include_prompt)
    except httpx.HTTPError as exc:
        return Response({"detail": _ollama_error(exc)}, status=503)
    return Response({"document_id": int(document_id), "question": question, **result})


def _sse(event: str, data) -> str:
    """Formats a single Server-Sent Event. We JSON-encode the data so there are no raw
    newlines (which would break the SSE protocol)."""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@csrf_exempt
def ask_stream(request):
    """
    Streaming RAG answer (Stage 5) over Server-Sent Events.
    Sends: 1 `sources` event (for the citations) → many `token` events → `done`.
    A plain Django view (not DRF), so rendering doesn't interfere with the stream.
    """
    if request.method != "POST":
        return JsonResponse({"detail": "POST only."}, status=405)

    body = json.loads(request.body or "{}")
    document_id = body.get("document_id")
    question = (body.get("question") or "").strip()
    k = int(body.get("k", 5))

    if not document_id or not question:
        return JsonResponse({"detail": "Both 'document_id' and 'question' are required."}, status=400)
    if not Document.objects.filter(pk=document_id).exists():
        return JsonResponse({"detail": f"No document with id={document_id}."}, status=404)

    try:
        messages, sources = prepare(document_id, question, k)
    except httpx.HTTPError as exc:
        return JsonResponse({"detail": _ollama_error(exc)}, status=503)

    def event_stream():
        # Citations first — the frontend has them ready before the answer starts flowing.
        yield _sse("sources", sources)
        # Then the live tokens. If Ollama dies mid-stream — we send an error event.
        try:
            for token in stream_chat(messages):
                yield _sse("token", {"text": token})
        except httpx.HTTPError as exc:
            yield _sse("error", {"detail": _ollama_error(exc)})
        yield _sse("done", {})

    response = StreamingHttpResponse(event_stream(), content_type="text/event-stream")
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"  # disables buffering on reverse proxies
    return response
