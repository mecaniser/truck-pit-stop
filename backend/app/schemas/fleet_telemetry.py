from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class TelemetryCapture(BaseModel):
    model_config = ConfigDict(
        extra="forbid", str_strip_whitespace=True, allow_inf_nan=False
    )
    client_request_id: UUID
    fleet_customer_id: UUID
    vin: str = Field(min_length=17, max_length=17)
    observed_at: datetime | None = None
    source_age_text: str | None = Field(None, max_length=120)
    provider_company_label: str | None = Field(None, max_length=255)
    provider_vehicle_id: str | None = Field(None, max_length=120)
    provider_vehicle_number: str | None = Field(None, max_length=120)
    location_label: str | None = Field(None, max_length=500)
    lat: float | None = Field(None, ge=-90, le=90)
    lng: float | None = Field(None, ge=-180, le=180)
    speed_mph: float | None = Field(None, ge=0, le=250)
    odometer_miles: float | None = Field(None, ge=0, le=100000000)
    engine_hours: float | None = Field(None, ge=0, le=10000000)
    fuel_percent: float | None = Field(None, ge=0, le=100)
    fault_count: int | None = Field(None, ge=0, le=2147483647, strict=True)
    evidence_note: str | None = Field(None, max_length=1000)

    @field_validator("*", mode="before")
    @classmethod
    def safe_text(cls, value):
        if isinstance(value, str) and (
            "\x00" in value or any(0xD800 <= ord(c) <= 0xDFFF for c in value)
        ):
            raise ValueError("Invalid text")
        return value

    @field_validator(
        "lat",
        "lng",
        "speed_mph",
        "odometer_miles",
        "engine_hours",
        "fuel_percent",
        mode="before",
    )
    @classmethod
    def numeric(cls, value):
        if isinstance(value, bool):
            raise ValueError("Invalid measurement")  # noqa: TRY004
        return value

    @field_validator(
        "source_age_text",
        "provider_company_label",
        "provider_vehicle_id",
        "provider_vehicle_number",
        "location_label",
        "evidence_note",
    )
    @classmethod
    def empty_text(cls, value):
        return value or None

    @field_validator("observed_at", mode="before")
    @classmethod
    def timestamp_type(cls, value):
        if value is not None and not isinstance(value, (str, datetime)):
            raise ValueError("Explicit timezone required")
        return value

    @field_validator("vin")
    @classmethod
    def normalize_vin(cls, value):
        import re

        value = value.upper()
        if not re.fullmatch(r"[A-HJ-NPR-Z0-9]{17}", value):
            raise ValueError("Invalid VIN")
        return value

    @model_validator(mode="after")
    def valid(self):
        if (self.lat is None) != (self.lng is None):
            raise ValueError("Coordinates require both values")
        if self.observed_at is not None:
            if self.observed_at.tzinfo is None:
                raise ValueError("Timezone required")
            self.observed_at = self.observed_at.astimezone(timezone.utc)
        if not self.location_label and all(
            getattr(self, f) is None
            for f in (
                "lat",
                "speed_mph",
                "odometer_miles",
                "engine_hours",
                "fuel_percent",
                "fault_count",
            )
        ):
            raise ValueError("Measurement required")
        return self


class ReadingProvenance(BaseModel):
    source: Literal["motive_api", "motive_dashboard_manual", "manual_location"]
    observed_at: datetime | None = None
    captured_at: datetime | None = None
    freshness: Literal["fresh", "delayed", "stale", "unknown"]
    snapshot_id: str | None = None
    source_age_text: str | None = None


class NumericReading(ReadingProvenance):
    value: float
    unit: Literal["mph", "mi", "h", "percent", "count"]
    basis: Literal["calibrated", "virtual", "dashboard_unspecified"] | None = None


class LocationReading(ReadingProvenance):
    lat: float | None = None
    lng: float | None = None
    label: str | None = None


class FleetTelemetry(BaseModel):
    location: LocationReading | None = None
    speed: NumericReading | None = None
    odometer: NumericReading | None = None
    engine_hours: NumericReading | None = None
    fuel: NumericReading | None = None
    fault_count: NumericReading | None = None
    motion: Literal["moving", "stopped", "unknown"] = "unknown"
