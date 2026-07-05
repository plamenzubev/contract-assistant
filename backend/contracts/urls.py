from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register(r"documents", views.DocumentViewSet, basename="document")

urlpatterns = [
    path("health/", views.health, name="health"),
    path("search/", views.search, name="search"),
    path("ask/", views.ask, name="ask"),
    path("ask/stream/", views.ask_stream, name="ask_stream"),
    path("", include(router.urls)),
]
