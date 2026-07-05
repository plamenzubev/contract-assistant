from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    # All API routes live under /api/ and are defined in the contracts app.
    path("api/", include("contracts.urls")),
]
