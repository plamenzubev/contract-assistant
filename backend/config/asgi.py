import os

from django.core.asgi import get_asgi_application

# ASGI entry point — needed for streaming (SSE) in Stage 5.
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
application = get_asgi_application()
