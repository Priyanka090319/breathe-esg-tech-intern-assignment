from __future__ import annotations

import csv
import io
import math
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from django.db import transaction
from django.utils.dateparse import parse_date

from .models import (
    DataRowStatus,
    EmissionScope,
    IngestionSource,
    NormalizedDataRow,
    Organization,
    RawDataPayload,
)


def _to_decimal(raw: Any) -> Decimal:
    if raw is None:
        raise ValueError("missing numeric value")
    text = str(raw).strip().replace(",", ".")
    if not text:
        raise ValueError("empty numeric value")
    try:
        return Decimal(text)
    except InvalidOperation as exc:
        raise ValueError(f"invalid numeric value '{raw}'") from exc


def _parse_required_date(raw: Any, field_name: str) -> date:
    if raw is None:
        raise ValueError(f"missing date for {field_name}")
    parsed = parse_date(str(raw).strip())
    if parsed is None:
        raise ValueError(f"unparseable date '{raw}' for {field_name}")
    return parsed


def _create_row(
    *,
    organization: Organization,
    ingestion_source: IngestionSource,
    raw_payload: RawDataPayload,
    actor: Any,
    scope: str,
    category: str,
    original_value: Decimal,
    original_unit: str,
    normalized_value: Decimal,
    normalized_unit: str,
    conversion_factor: Decimal,
    conversion_reference: str,
    activity_date: date,
    status: str,
    status_note: str = "",
) -> NormalizedDataRow:
    return NormalizedDataRow.objects.create(
        organization=organization,
        ingestion_source=ingestion_source,
        raw_payload=raw_payload,
        scope=scope,
        category=category,
        original_value=original_value,
        original_unit=original_unit,
        normalized_value=normalized_value,
        normalized_unit=normalized_unit,
        conversion_factor=conversion_factor,
        conversion_reference=conversion_reference,
        activity_date=activity_date,
        status=status,
        status_note=status_note,
        last_modified_by=actor,
    )


def _create_failed_row(
    *,
    organization: Organization,
    ingestion_source: IngestionSource,
    raw_payload: RawDataPayload,
    actor: Any,
    activity_date: date | None,
    category: str,
    error_reason: str,
    scope: str = EmissionScope.SCOPE_3,
) -> NormalizedDataRow:
    fallback_date = activity_date or date.today()
    return _create_row(
        organization=organization,
        ingestion_source=ingestion_source,
        raw_payload=raw_payload,
        actor=actor,
        scope=scope,
        category=category,
        original_value=Decimal("0"),
        original_unit="UNKNOWN",
        normalized_value=Decimal("0"),
        normalized_unit="MTCO2E",
        conversion_factor=Decimal("0"),
        conversion_reference="validation_error",
        activity_date=fallback_date,
        status=DataRowStatus.FAILED_VALIDATION,
        status_note=error_reason[:4000],
    )


def _iter_csv_rows(raw_payload: RawDataPayload) -> list[dict[str, str]]:
    payload = raw_payload.raw_payload
    if isinstance(payload, list):
        return [dict(item) for item in payload if isinstance(item, dict)]

    if isinstance(payload, dict) and isinstance(payload.get("rows"), list):
        return [dict(item) for item in payload["rows"] if isinstance(item, dict)]

    if isinstance(payload, str):
        stream = io.StringIO(payload)
        reader = csv.DictReader(stream)
        return [dict(row) for row in reader]

    raise ValueError("Unsupported raw_payload format for CSV parser.")


class SAPFuelProcurementParser:
    """
    Parses SAP flat-file exports with German headers into NormalizedDataRow.
    """

    UNIT_TO_STANDARD = {
        "L": ("LITER", Decimal("1")),
        "LITER": ("LITER", Decimal("1")),
        "KG": ("KILOGRAM", Decimal("1")),
        "KILOGRAM": ("KILOGRAM", Decimal("1")),
    }

    # Example factors in tCO2e per standard unit.
    EMISSION_FACTORS = {
        "LITER": Decimal("0.00268"),
        "KILOGRAM": Decimal("0.00300"),
    }

    PLANT_LOOKUP = {
        "DE_01": (EmissionScope.SCOPE_1, "Stationary Combustion"),
        "DE_02": (EmissionScope.SCOPE_1, "Mobile Combustion"),
        "FR_01": (EmissionScope.SCOPE_1, "Stationary Combustion"),
    }

    REQUIRED_HEADERS = {"Materialnummer", "Menge", "Einheit", "Werk", "Buchungsdatum"}

    @classmethod
    @transaction.atomic
    def parse_and_persist(
        cls,
        *,
        organization: Organization,
        ingestion_source: IngestionSource,
        raw_payload: RawDataPayload,
        actor: Any = None,
    ) -> list[NormalizedDataRow]:
        rows = _iter_csv_rows(raw_payload)
        created: list[NormalizedDataRow] = []
        for idx, row in enumerate(rows, start=1):
            created.append(
                cls._parse_single_row(
                    organization=organization,
                    ingestion_source=ingestion_source,
                    raw_payload=raw_payload,
                    actor=actor,
                    row=row,
                    row_number=idx,
                )
            )
        return created

    @classmethod
    def _parse_single_row(
        cls,
        *,
        organization: Organization,
        ingestion_source: IngestionSource,
        raw_payload: RawDataPayload,
        actor: Any,
        row: dict[str, Any],
        row_number: int,
    ) -> NormalizedDataRow:
        try:
            missing = [header for header in cls.REQUIRED_HEADERS if not str(row.get(header, "")).strip()]
            if missing:
                raise ValueError(f"missing required fields: {', '.join(missing)}")

            unit_raw = str(row["Einheit"]).strip().upper()
            if unit_raw not in cls.UNIT_TO_STANDARD:
                raise ValueError(f"unsupported unit '{unit_raw}'")

            plant_code = str(row["Werk"]).strip()
            if plant_code not in cls.PLANT_LOOKUP:
                raise ValueError(f"unknown plant code '{plant_code}'")

            activity_date = _parse_required_date(row["Buchungsdatum"], "Buchungsdatum")
            original_value = _to_decimal(row["Menge"])

            standard_unit, to_standard_factor = cls.UNIT_TO_STANDARD[unit_raw]
            standard_amount = original_value * to_standard_factor
            emission_factor = cls.EMISSION_FACTORS[standard_unit]
            normalized_value = standard_amount * emission_factor

            scope, category = cls.PLANT_LOOKUP[plant_code]
            conversion_factor = to_standard_factor * emission_factor
            conversion_reference = f"SAP_UNIT_X_EMISSION_FACTOR:{standard_unit}"
            material_code = str(row["Materialnummer"]).strip()
            category_full = f"{category} | Plant:{plant_code} | Material:{material_code}"

            return _create_row(
                organization=organization,
                ingestion_source=ingestion_source,
                raw_payload=raw_payload,
                actor=actor,
                scope=scope,
                category=category_full,
                original_value=original_value,
                original_unit=unit_raw,
                normalized_value=normalized_value,
                normalized_unit="MTCO2E",
                conversion_factor=conversion_factor,
                conversion_reference=conversion_reference,
                activity_date=activity_date,
                status=DataRowStatus.INGESTED,
            )
        except Exception as exc:
            parsed_date = parse_date(str(row.get("Buchungsdatum", "")).strip()) if row.get("Buchungsdatum") else None
            return _create_failed_row(
                organization=organization,
                ingestion_source=ingestion_source,
                raw_payload=raw_payload,
                actor=actor,
                activity_date=parsed_date,
                category=f"SAP row {row_number}",
                error_reason=f"SAP parse failure on row {row_number}: {exc}",
                scope=EmissionScope.SCOPE_1,
            )


@dataclass(frozen=True)
class BillingPeriod:
    start: date
    end: date

    def overlaps(self, other: "BillingPeriod") -> bool:
        return self.start <= other.end and other.start <= self.end


class UtilityPortalCSVParser:
    REQUIRED_HEADERS = {"Meter_ID", "Start_Date", "End_Date", "Usage_kWh", "Tariff_Code"}
    SPIKE_MULTIPLIER = Decimal("1.5")

    @classmethod
    @transaction.atomic
    def parse_and_persist(
        cls,
        *,
        organization: Organization,
        ingestion_source: IngestionSource,
        raw_payload: RawDataPayload,
        actor: Any = None,
    ) -> list[NormalizedDataRow]:
        rows = _iter_csv_rows(raw_payload)
        created: list[NormalizedDataRow] = []
        periods_seen: dict[str, list[BillingPeriod]] = {}
        for idx, row in enumerate(rows, start=1):
            created.append(
                cls._parse_single_row(
                    organization=organization,
                    ingestion_source=ingestion_source,
                    raw_payload=raw_payload,
                    actor=actor,
                    row=row,
                    row_number=idx,
                    periods_seen=periods_seen,
                )
            )
        return created

    @classmethod
    def _parse_single_row(
        cls,
        *,
        organization: Organization,
        ingestion_source: IngestionSource,
        raw_payload: RawDataPayload,
        actor: Any,
        row: dict[str, Any],
        row_number: int,
        periods_seen: dict[str, list[BillingPeriod]],
    ) -> NormalizedDataRow:
        try:
            missing = [header for header in cls.REQUIRED_HEADERS if not str(row.get(header, "")).strip()]
            if missing:
                raise ValueError(f"missing required fields: {', '.join(missing)}")

            meter_id = str(row["Meter_ID"]).strip()
            tariff_code = str(row["Tariff_Code"]).strip()
            start = _parse_required_date(row["Start_Date"], "Start_Date")
            end = _parse_required_date(row["End_Date"], "End_Date")
            if end < start:
                raise ValueError("End_Date earlier than Start_Date")

            usage_kwh = _to_decimal(row["Usage_kWh"])
            if usage_kwh < 0:
                raise ValueError("Usage_kWh cannot be negative")

            current_period = BillingPeriod(start=start, end=end)
            suspicious_reasons: list[str] = []

            if cls._has_overlap(
                organization=organization,
                meter_id=meter_id,
                candidate=current_period,
                periods_seen=periods_seen.get(meter_id, []),
            ):
                suspicious_reasons.append("overlapping billing period")

            if cls._is_spike(organization=organization, meter_id=meter_id, usage_kwh=usage_kwh):
                suspicious_reasons.append("consumption spike >150% of historical average")

            periods_seen.setdefault(meter_id, []).append(current_period)

            status = DataRowStatus.INGESTED
            status_note = f"Tariff:{tariff_code} Period:{start.isoformat()}->{end.isoformat()}"
            if suspicious_reasons:
                status = DataRowStatus.FLAGGED_SUSPICIOUS
                status_note = f"{status_note}; Flags: {', '.join(suspicious_reasons)}"

            category = f"ELECTRICITY_METER:{meter_id}"
            return _create_row(
                organization=organization,
                ingestion_source=ingestion_source,
                raw_payload=raw_payload,
                actor=actor,
                scope=EmissionScope.SCOPE_2,
                category=category,
                original_value=usage_kwh,
                original_unit="KWH",
                normalized_value=usage_kwh,
                normalized_unit="KWH",
                conversion_factor=Decimal("1"),
                conversion_reference="utility_native_kwh",
                activity_date=end,
                status=status,
                status_note=status_note,
            )
        except Exception as exc:
            parsed_end = parse_date(str(row.get("End_Date", "")).strip()) if row.get("End_Date") else None
            return _create_failed_row(
                organization=organization,
                ingestion_source=ingestion_source,
                raw_payload=raw_payload,
                actor=actor,
                activity_date=parsed_end,
                category=f"Utility row {row_number}",
                error_reason=f"Utility parse failure on row {row_number}: {exc}",
                scope=EmissionScope.SCOPE_2,
            )

    @classmethod
    def _has_overlap(
        cls,
        *,
        organization: Organization,
        meter_id: str,
        candidate: BillingPeriod,
        periods_seen: list[BillingPeriod],
    ) -> bool:
        for seen in periods_seen:
            if candidate.overlaps(seen):
                return True

        category = f"ELECTRICITY_METER:{meter_id}"
        # Existing rows only store activity_date (period end), so this catches duplicate month/end clashes.
        if NormalizedDataRow.objects.filter(
            organization=organization,
            scope=EmissionScope.SCOPE_2,
            category=category,
            activity_date__range=(candidate.start, candidate.end),
        ).exclude(status=DataRowStatus.FAILED_VALIDATION).exists():
            return True
        return False

    @classmethod
    def _is_spike(cls, *, organization: Organization, meter_id: str, usage_kwh: Decimal) -> bool:
        category = f"ELECTRICITY_METER:{meter_id}"
        historical_values = list(
            NormalizedDataRow.objects.filter(
                organization=organization,
                scope=EmissionScope.SCOPE_2,
                category=category,
            )
            .exclude(status__in=[DataRowStatus.FAILED_VALIDATION, DataRowStatus.LOCKED_FOR_AUDIT])
            .values_list("normalized_value", flat=True)[:24]
        )
        if not historical_values:
            return False

        avg = sum(historical_values) / Decimal(len(historical_values))
        if avg <= 0:
            return False
        return usage_kwh > (avg * cls.SPIKE_MULTIPLIER)


class CorporateTravelJSONParser:
    REQUIRED_FIELDS = {
        "employee_id",
        "trip_purpose",
        "origin_airport",
        "destination_airport",
        "cabin_class",
    }

    # Approx lat/lon lookup. Expand as needed.
    AIRPORT_COORDS = {
        "JFK": (40.6413, -73.7781),
        "LHR": (51.4700, -0.4543),
        "FRA": (50.0379, 8.5622),
        "DEL": (28.5562, 77.1000),
        "SFO": (37.6213, -122.3790),
        "CDG": (49.0097, 2.5479),
    }

    CABIN_MULTIPLIER = {
        "ECONOMY": Decimal("1.0"),
        "BUSINESS": Decimal("1.8"),
    }

    # tCO2e per passenger-km base factor.
    BASE_TCO2E_PER_KM = Decimal("0.00009")

    @classmethod
    @transaction.atomic
    def parse_and_persist(
        cls,
        *,
        organization: Organization,
        ingestion_source: IngestionSource,
        raw_payload: RawDataPayload,
        actor: Any = None,
    ) -> list[NormalizedDataRow]:
        payload = raw_payload.raw_payload
        if isinstance(payload, dict):
            trips = payload.get("trips", [])
        elif isinstance(payload, list):
            trips = payload
        else:
            raise ValueError("Unsupported raw_payload format for travel parser.")

        created: list[NormalizedDataRow] = []
        for idx, trip in enumerate(trips, start=1):
            created.append(
                cls._parse_single_trip(
                    organization=organization,
                    ingestion_source=ingestion_source,
                    raw_payload=raw_payload,
                    actor=actor,
                    trip=trip,
                    row_number=idx,
                )
            )
        return created

    @classmethod
    def _parse_single_trip(
        cls,
        *,
        organization: Organization,
        ingestion_source: IngestionSource,
        raw_payload: RawDataPayload,
        actor: Any,
        trip: dict[str, Any],
        row_number: int,
    ) -> NormalizedDataRow:
        try:
            if not isinstance(trip, dict):
                raise ValueError("trip entry is not a JSON object")

            missing = [key for key in cls.REQUIRED_FIELDS if not str(trip.get(key, "")).strip()]
            if missing:
                raise ValueError(f"missing required fields: {', '.join(missing)}")

            origin = str(trip["origin_airport"]).strip().upper()
            destination = str(trip["destination_airport"]).strip().upper()
            if origin == destination:
                raise ValueError("origin and destination airports cannot be identical")

            cabin = str(trip["cabin_class"]).strip().upper()
            if cabin not in cls.CABIN_MULTIPLIER:
                raise ValueError(f"unsupported cabin_class '{trip['cabin_class']}'")

            distance_km = cls._distance_km(origin, destination)
            multiplier = cls.CABIN_MULTIPLIER[cabin]
            conversion_factor = cls.BASE_TCO2E_PER_KM * multiplier
            normalized_value = Decimal(distance_km) * conversion_factor

            employee_id = str(trip["employee_id"]).strip()
            purpose = str(trip["trip_purpose"]).strip()
            category = f"Business Travel | Employee:{employee_id} | Purpose:{purpose}"

            return _create_row(
                organization=organization,
                ingestion_source=ingestion_source,
                raw_payload=raw_payload,
                actor=actor,
                scope=EmissionScope.SCOPE_3,
                category=category,
                original_value=Decimal(distance_km),
                original_unit="KM",
                normalized_value=normalized_value,
                normalized_unit="MTCO2E",
                conversion_factor=conversion_factor,
                conversion_reference=f"flight_distance_x_factor:{origin}-{destination}:{cabin}",
                activity_date=raw_payload.ingestion_timestamp.date(),
                status=DataRowStatus.INGESTED,
            )
        except Exception as exc:
            return _create_failed_row(
                organization=organization,
                ingestion_source=ingestion_source,
                raw_payload=raw_payload,
                actor=actor,
                activity_date=raw_payload.ingestion_timestamp.date(),
                category=f"Travel row {row_number}",
                error_reason=f"Travel parse failure on row {row_number}: {exc}",
                scope=EmissionScope.SCOPE_3,
            )

    @classmethod
    def _distance_km(cls, origin: str, destination: str) -> int:
        if origin not in cls.AIRPORT_COORDS:
            raise ValueError(f"unknown origin airport '{origin}'")
        if destination not in cls.AIRPORT_COORDS:
            raise ValueError(f"unknown destination airport '{destination}'")

        lat1, lon1 = cls.AIRPORT_COORDS[origin]
        lat2, lon2 = cls.AIRPORT_COORDS[destination]
        return int(round(cls._haversine_km(lat1, lon1, lat2, lon2)))

    @staticmethod
    def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        radius_km = 6371.0
        d_lat = math.radians(lat2 - lat1)
        d_lon = math.radians(lon2 - lon1)
        a = (
            math.sin(d_lat / 2) ** 2
            + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(d_lon / 2) ** 2
        )
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        return radius_km * c
