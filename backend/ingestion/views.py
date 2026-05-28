import csv
import io

from django.db import transaction
from django.utils import timezone
from rest_framework import mixins, status, viewsets
from rest_framework import serializers as drf_serializers
from rest_framework import permissions
from rest_framework.decorators import action
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import (
    DataRowStatus,
    IngestionSource,
    NormalizedDataRow,
    Organization,
    RawDataPayload,
)
from .parsers import SAPFuelProcurementParser, UtilityPortalCSVParser
from .serializers import NormalizedDataRowSerializer


class TenantResolutionMixin:
    """
    Resolves organization from authenticated user context or explicit request input.
    """

    def _resolve_organization(self, request) -> Organization:
        user_org_id = getattr(request.user, "organization_id", None)
        if user_org_id:
            return Organization.objects.get(id=user_org_id, is_active=True)

        org_id = request.query_params.get("organization_id") or request.data.get("organization_id")
        if not org_id:
            raise drf_serializers.ValidationError(
                {"organization_id": "organization_id is required for tenant-scoped operations."}
            )
        try:
            return Organization.objects.get(id=org_id, is_active=True)
        except Organization.DoesNotExist as exc:
            raise drf_serializers.ValidationError({"organization_id": "Invalid organization_id."}) from exc

    @staticmethod
    def _normalize_status(raw_status: str) -> str:
        normalized = (raw_status or "").strip().upper()
        normalized = normalized.replace("-", "_").replace(" ", "_")
        if normalized in DataRowStatus.values:
            return normalized
        raise drf_serializers.ValidationError({"status": f"Unsupported status '{raw_status}'."})


class NormalizedDataRowViewSet(
    TenantResolutionMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    """
    Analyst dashboard viewset:
    - List/retrieve normalized rows
    - Filter by status and ingestion source
    - approve_row action
    - lock_dataset action
    """

    serializer_class = NormalizedDataRowSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        organization = self._resolve_organization(self.request)
        queryset = (
            NormalizedDataRow.objects.filter(organization=organization)
            .select_related("ingestion_source", "raw_payload")
            .order_by("-activity_date", "-id")
        )

        status_filter = self.request.query_params.get("status")
        if status_filter:
            queryset = queryset.filter(status=self._normalize_status(status_filter))

        ingestion_source_id = self.request.query_params.get("ingestion_source")
        if ingestion_source_id:
            queryset = queryset.filter(ingestion_source_id=ingestion_source_id)
        return queryset

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def approve_row(self, request, pk=None):
        row = self.get_object()
        if row.status not in {DataRowStatus.INGESTED, DataRowStatus.FLAGGED_SUSPICIOUS}:
            return Response(
                {
                    "detail": "Only INGESTED or FLAGGED_SUSPICIOUS rows can be approved.",
                    "current_status": row.status,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        now = timezone.now()
        row.status = DataRowStatus.ANALYST_APPROVED
        row.approved_by = request.user
        row.approved_at = now
        row.last_modified_by = request.user
        row.status_note = (row.status_note or "")[:3500] + " | Approved by analyst"
        row.save()
        return Response(self.get_serializer(row).data, status=status.HTTP_200_OK)

    @action(detail=False, methods=["post"])
    @transaction.atomic
    def lock_dataset(self, request):
        organization = self._resolve_organization(request)
        approved_rows = NormalizedDataRow.objects.filter(
            organization=organization,
            status=DataRowStatus.ANALYST_APPROVED,
        ).select_for_update()

        now = timezone.now()
        locked_count = 0
        for row in approved_rows:
            row.status = DataRowStatus.LOCKED_FOR_AUDIT
            row.locked_by = request.user
            row.locked_at = now
            row.last_modified_by = request.user
            row.status_note = (row.status_note or "")[:3500] + " | Locked for audit"
            row.save()
            locked_count += 1

        return Response(
            {
                "organization_id": organization.id,
                "locked_count": locked_count,
                "status": DataRowStatus.LOCKED_FOR_AUDIT,
            },
            status=status.HTTP_200_OK,
        )


class IngestionFileUploadAPIView(TenantResolutionMixin, APIView):
    """
    Multipart upload endpoint for parser-specific ingestion.
    POST /api/ingest/file/
    """

    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser]

    @transaction.atomic
    def post(self, request):
        organization = self._resolve_organization(request)
        file_obj = request.FILES.get("file")
        file_type = (request.data.get("file_type") or "").strip().lower()
        ingestion_source_id = request.data.get("ingestion_source_id")

        if not file_obj:
            raise drf_serializers.ValidationError({"file": "A file is required."})
        if file_type not in {"sap_export", "utility_portal"}:
            raise drf_serializers.ValidationError(
                {"file_type": "file_type must be either 'sap_export' or 'utility_portal'."}
            )
        if not ingestion_source_id:
            raise drf_serializers.ValidationError({"ingestion_source_id": "ingestion_source_id is required."})

        try:
            source = IngestionSource.objects.get(
                id=ingestion_source_id,
                organization=organization,
                is_active=True,
            )
        except IngestionSource.DoesNotExist as exc:
            raise drf_serializers.ValidationError(
                {"ingestion_source_id": "Invalid source for this organization."}
            ) from exc

        decoded = file_obj.read().decode("utf-8-sig")
        raw_payload_obj = RawDataPayload.objects.create(
            organization=organization,
            ingestion_source=source,
            original_filename=file_obj.name,
            original_endpoint="",
            raw_payload=decoded,
            received_by=request.user,
        )

        if file_type == "sap_export":
            rows = SAPFuelProcurementParser.parse_and_persist(
                organization=organization,
                ingestion_source=source,
                raw_payload=raw_payload_obj,
                actor=request.user,
            )
        else:
            rows = UtilityPortalCSVParser.parse_and_persist(
                organization=organization,
                ingestion_source=source,
                raw_payload=raw_payload_obj,
                actor=request.user,
            )

        serializer = NormalizedDataRowSerializer(rows, many=True)
        return Response(
            {
                "raw_payload_id": raw_payload_obj.id,
                "ingested_count": len(rows),
                "failed_validation_count": len(
                    [row for row in rows if row.status == DataRowStatus.FAILED_VALIDATION]
                ),
                "flagged_suspicious_count": len(
                    [row for row in rows if row.status == DataRowStatus.FLAGGED_SUSPICIOUS]
                ),
                "rows": serializer.data,
            },
            status=status.HTTP_201_CREATED,
        )
