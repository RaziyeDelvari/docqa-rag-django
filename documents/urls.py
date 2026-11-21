from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import AskView, DocumentViewSet, HistoryViewSet

router = DefaultRouter()
router.register("documents", DocumentViewSet, basename="document")
router.register("history", HistoryViewSet, basename="history")

urlpatterns = [path("ask/", AskView.as_view(), name="ask")] + router.urls
