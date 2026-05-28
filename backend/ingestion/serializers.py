from rest_framework import serializers

from .models import IngestionSource, NormalizedDataRow


class IngestionSourceNestedSerializer(serializers.ModelSerializer):
    source_type_display = serializers.CharField(source="get_source_type_display", read_only=True)
    mechanism_display = serializers.CharField(source="get_mechanism_display", read_only=True)

    class Meta:
        model = IngestionSource
        fields = (
            "id",
            "name",
            "source_type",
            "source_type_display",
            "mechanism",
            "mechanism_display",
            "endpoint_or_location",
            "is_active",
        )


class NormalizedDataRowSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    scope_display = serializers.CharField(source="get_scope_display", read_only=True)
    ingestion_source = IngestionSourceNestedSerializer(read_only=True)
    raw_payload_id = serializers.IntegerField(source="raw_payload.id", read_only=True)

    class Meta:
        model = NormalizedDataRow
        fields = (
            "id",
            "organization",
            "ingestion_source",
            "raw_payload_id",
            "scope",
            "scope_display",
            "category",
            "original_value",
            "original_unit",
            "normalized_value",
            "normalized_unit",
            "conversion_factor",
            "conversion_reference",
            "activity_date",
            "status",
            "status_display",
            "status_note",
            "last_modified_by",
            "last_modified_at",
            "approved_by",
            "approved_at",
            "locked_by",
            "locked_at",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields
