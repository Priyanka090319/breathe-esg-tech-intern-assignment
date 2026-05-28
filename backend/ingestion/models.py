from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Organization(TimeStampedModel):
    """
    Tenant root model. Every business record must attach to an Organization.
    """

    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=100, unique=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "organization"
        indexes = [
            models.Index(fields=["slug"], name="idx_org_slug"),
            models.Index(fields=["is_active"], name="idx_org_active"),
        ]

    def __str__(self) -> str:
        return self.name


class IngestionSourceType(models.TextChoices):
    SAP = "SAP", "SAP"
    UTILITY = "UTILITY", "Utility"
    TRAVEL = "TRAVEL", "Travel"
    API = "API", "API"
    FILE_UPLOAD = "FILE_UPLOAD", "File Upload"
    OTHER = "OTHER", "Other"


class IngestionMechanism(models.TextChoices):
    SFTP = "SFTP", "SFTP"
    REST_API = "REST_API", "REST API"
    MANUAL_UPLOAD = "MANUAL_UPLOAD", "Manual Upload"
    WEBHOOK = "WEBHOOK", "Webhook"
    BATCH_JOB = "BATCH_JOB", "Batch Job"


class IngestionSource(TimeStampedModel):
    """
    Integration source metadata scoped to a tenant.
    """

    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="ingestion_sources",
    )
    source_type = models.CharField(max_length=20, choices=IngestionSourceType.choices)
    mechanism = models.CharField(max_length=20, choices=IngestionMechanism.choices)
    name = models.CharField(max_length=255)
    endpoint_or_location = models.CharField(
        max_length=1024,
        help_text="API endpoint, bucket path, SFTP path, etc.",
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "ingestion_source"
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "name"],
                name="uq_ingestion_source_org_name",
            )
        ]
        indexes = [
            models.Index(fields=["organization"], name="idx_source_org"),
            models.Index(fields=["organization", "source_type"], name="idx_source_org_type"),
        ]

    def __str__(self) -> str:
        return f"{self.organization.slug}:{self.name}"


class RawDataPayload(TimeStampedModel):
    """
    Immutable log of incoming data for lineage/debug.
    """

    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="raw_payloads",
    )
    ingestion_source = models.ForeignKey(
        IngestionSource,
        on_delete=models.PROTECT,
        related_name="raw_payloads",
    )
    ingestion_timestamp = models.DateTimeField(default=timezone.now, db_index=True)
    original_filename = models.CharField(max_length=512, blank=True, default="")
    original_endpoint = models.CharField(max_length=1024, blank=True, default="")
    request_id = models.CharField(max_length=128, blank=True, default="", db_index=True)
    checksum_sha256 = models.CharField(max_length=64, blank=True, default="", db_index=True)
    raw_payload = models.JSONField()
    received_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="received_raw_payloads",
    )

    class Meta:
        db_table = "raw_data_payload"
        indexes = [
            models.Index(fields=["organization"], name="idx_raw_org"),
            models.Index(fields=["ingestion_timestamp"], name="idx_raw_ingested_at"),
            models.Index(fields=["organization", "ingestion_timestamp"], name="idx_raw_org_ingested"),
        ]

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise ValidationError("RawDataPayload is immutable and cannot be updated.")
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"Payload<{self.id}> org={self.organization_id}"


class EmissionScope(models.TextChoices):
    SCOPE_1 = "SCOPE_1", "Scope 1 (Direct)"
    SCOPE_2 = "SCOPE_2", "Scope 2 (Energy Indirect)"
    SCOPE_3 = "SCOPE_3", "Scope 3 (Value Chain)"


class DataRowStatus(models.TextChoices):
    INGESTED = "INGESTED", "Ingested"
    FLAGGED_SUSPICIOUS = "FLAGGED_SUSPICIOUS", "Flagged Suspicious"
    FAILED_VALIDATION = "FAILED_VALIDATION", "Failed Validation"
    ANALYST_APPROVED = "ANALYST_APPROVED", "Analyst Approved"
    LOCKED_FOR_AUDIT = "LOCKED_FOR_AUDIT", "Locked For Audit"


class NormalizedDataRow(TimeStampedModel):
    """
    Main emissions record with normalization + state machine + audit data.
    """

    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="normalized_rows",
    )
    raw_payload = models.ForeignKey(
        RawDataPayload,
        on_delete=models.PROTECT,
        related_name="normalized_rows",
    )
    ingestion_source = models.ForeignKey(
        IngestionSource,
        on_delete=models.PROTECT,
        related_name="normalized_rows",
    )

    scope = models.CharField(max_length=10, choices=EmissionScope.choices, db_index=True)
    category = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Optional sub-category (e.g. Purchased Electricity, Business Travel).",
    )

    original_value = models.DecimalField(max_digits=24, decimal_places=8)
    original_unit = models.CharField(max_length=64)

    normalized_value = models.DecimalField(
        max_digits=24,
        decimal_places=8,
        help_text="Converted value in canonical unit.",
    )
    normalized_unit = models.CharField(
        max_length=64,
        help_text="Canonical unit, e.g. MTCO2E, KWH, LITER.",
    )
    conversion_factor = models.DecimalField(
        max_digits=24,
        decimal_places=12,
        help_text="Exact factor used: original_value * conversion_factor = normalized_value.",
    )
    conversion_reference = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Factor source/version (e.g. DEFRA 2026 v1.2).",
    )

    activity_date = models.DateField(db_index=True)

    status = models.CharField(
        max_length=24,
        choices=DataRowStatus.choices,
        default=DataRowStatus.INGESTED,
        db_index=True,
    )
    status_note = models.TextField(blank=True, default="")
    last_modified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="modified_emission_rows",
    )
    last_modified_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_emission_rows",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    locked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="locked_emission_rows",
    )
    locked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "normalized_data_row"
        indexes = [
            models.Index(fields=["organization"], name="idx_norm_org"),
            models.Index(fields=["status"], name="idx_norm_status"),
            models.Index(fields=["organization", "status"], name="idx_norm_org_status"),
            models.Index(fields=["organization", "scope"], name="idx_norm_org_scope"),
            models.Index(fields=["organization", "activity_date"], name="idx_norm_org_activity_date"),
        ]

    _ALLOWED_TRANSITIONS = {
        DataRowStatus.INGESTED: {
            DataRowStatus.FLAGGED_SUSPICIOUS,
            DataRowStatus.FAILED_VALIDATION,
            DataRowStatus.ANALYST_APPROVED,
        },
        DataRowStatus.FLAGGED_SUSPICIOUS: {
            DataRowStatus.FAILED_VALIDATION,
            DataRowStatus.ANALYST_APPROVED,
        },
        DataRowStatus.FAILED_VALIDATION: {
            DataRowStatus.INGESTED,
            DataRowStatus.ANALYST_APPROVED,
        },
        DataRowStatus.ANALYST_APPROVED: {
            DataRowStatus.LOCKED_FOR_AUDIT,
        },
        DataRowStatus.LOCKED_FOR_AUDIT: set(),
    }

    def clean(self):
        if self.pk:
            prev = NormalizedDataRow.objects.only("status").get(pk=self.pk)

            if prev.status != self.status:
                if self.status not in self._ALLOWED_TRANSITIONS[prev.status]:
                    raise ValidationError(
                        {"status": f"Invalid status transition: {prev.status} -> {self.status}"}
                    )

            if prev.status == DataRowStatus.LOCKED_FOR_AUDIT:
                raise ValidationError("Locked rows cannot be modified.")

        if self.raw_payload_id and self.organization_id != self.raw_payload.organization_id:
            raise ValidationError("raw_payload organization mismatch.")
        if self.ingestion_source_id and self.organization_id != self.ingestion_source.organization_id:
            raise ValidationError("ingestion_source organization mismatch.")

    def save(self, *args, **kwargs):
        self.full_clean()
        self.last_modified_at = timezone.now()
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"NormalizedDataRow<{self.id}> {self.scope} {self.status}"


class DataCorrectionLog(TimeStampedModel):
    """
    Append-only corrections for analyst edits before approval/lock.
    """

    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="correction_logs",
    )
    data_row = models.ForeignKey(
        NormalizedDataRow,
        on_delete=models.CASCADE,
        related_name="corrections",
    )
    corrected_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="data_corrections",
    )
    corrected_at = models.DateTimeField(default=timezone.now, db_index=True)

    field_name = models.CharField(max_length=128)
    old_value = models.TextField(blank=True, default="")
    new_value = models.TextField(blank=True, default="")
    reason = models.TextField()

    class Meta:
        db_table = "data_correction_log"
        indexes = [
            models.Index(fields=["organization"], name="idx_corr_org"),
            models.Index(fields=["data_row"], name="idx_corr_row"),
            models.Index(fields=["organization", "corrected_at"], name="idx_corr_org_time"),
        ]

    def clean(self):
        if self.organization_id != self.data_row.organization_id:
            raise ValidationError("Correction log organization must match data row organization.")
        if self.data_row.status in {
            DataRowStatus.ANALYST_APPROVED,
            DataRowStatus.LOCKED_FOR_AUDIT,
        }:
            raise ValidationError("Corrections are only allowed on unapproved/unlocked rows.")

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"Correction<{self.id}> row={self.data_row_id} field={self.field_name}"
