from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import IngestionFileUploadAPIView, NormalizedDataRowViewSet

router = DefaultRouter()
router.register("normalized-rows", NormalizedDataRowViewSet, basename="normalized-data-row")

urlpatterns = [
    path("", include(router.urls)),
    path("ingest/file/", IngestionFileUploadAPIView.as_view(), name="ingestion-file-upload"),
]
