"""Source-report daily fuel; never silently merged with calculated trip estimates."""
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from typing import Literal
from uuid import UUID
from zoneinfo import ZoneInfo
import re
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from app.schemas.fleet_trip import explicit_timestamp


class FuelDailyImport(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, allow_inf_nan=False)
    vin: str
    unit: str = Field(min_length=1, max_length=120)
    provider_company_id: str = Field(min_length=1, max_length=120)
    provider_vehicle_id: str = Field(min_length=1, max_length=120)
    report_date: date
    source_timezone: str | None = Field(default=None, max_length=100)
    timezone_status: Literal["unverified", "verified"] = "unverified"
    driving_fuel_gallons: Decimal | None = Field(default=None, ge=0, le=10000)
    idling_fuel_gallons: Decimal | None = Field(default=None, ge=0, le=10000)
    reported_total_fuel_gallons: Decimal | None = Field(default=None, ge=0, le=20000)
    source_distance_miles: Decimal | None = Field(default=None, ge=0, le=100000)
    # Provider report durations may span more than the calendar date; preserve them
    # as source observations, never treat them as reconstructed elapsed intervals.
    source_driving_seconds: int | None = Field(default=None, ge=0, le=2678400, strict=True)
    source_idling_seconds: int | None = Field(default=None, ge=0, le=2678400, strict=True)
    source_read_at: datetime
    source_receipt_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    identity_receipt_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")

    @field_validator("vin")
    @classmethod
    def valid_vin(cls, value):
        value = value.upper()
        if not re.fullmatch(r"[A-HJ-NPR-Z0-9]{17}", value):
            raise ValueError("Verified 17-character VIN required")
        return value

    @field_validator("report_date", mode="before")
    @classmethod
    def explicit_date(cls, value):
        if isinstance(value, datetime) or not isinstance(value, (str, date)):
            raise ValueError("Explicit source report date required")
        if isinstance(value, str) and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            raise ValueError("Source report date must be YYYY-MM-DD")
        return value

    @field_validator("driving_fuel_gallons", "idling_fuel_gallons", "reported_total_fuel_gallons", "source_distance_miles", mode="before")
    @classmethod
    def no_bool(cls, value):
        if isinstance(value, bool):
            raise ValueError("Measurement must be numeric")
        return value

    @field_validator("driving_fuel_gallons", "idling_fuel_gallons", "reported_total_fuel_gallons", "source_distance_miles")
    @classmethod
    def finite_precision(cls, value):
        if value is not None and (not value.is_finite() or value != value.quantize(Decimal("0.001"))):
            raise ValueError("Finite source precision of at most three decimal places required")
        return value

    _explicit = field_validator("source_read_at", mode="before")(explicit_timestamp)

    @field_validator("source_read_at")
    @classmethod
    def aware(cls, value):
        if value.tzinfo is None:
            raise ValueError("Explicit timezone required")
        return value.astimezone(timezone.utc)

    @model_validator(mode="after")
    def valid_source(self):
        if self.timezone_status == "verified":
            if not self.source_timezone:
                raise ValueError("Verified timezone required")
            ZoneInfo(self.source_timezone)
        elif self.source_timezone is not None:
            raise ValueError("Unverified source timezone must remain null")
        if all(v is None for v in (self.driving_fuel_gallons, self.idling_fuel_gallons, self.reported_total_fuel_gallons)):
            raise ValueError("At least one source fuel reading required")
        if all(v is not None for v in (self.driving_fuel_gallons, self.idling_fuel_gallons, self.reported_total_fuel_gallons)):
            if abs(self.reported_total_fuel_gallons - self.driving_fuel_gallons - self.idling_fuel_gallons) > Decimal("0.15"):
                raise ValueError("Fuel components exceed source rounding tolerance")
        if self.report_date >= self.source_read_at.date():
            raise ValueError("Completed historical source date required")
        return self

    def membership_window(self):
        midnight = datetime.combine(self.report_date, time.min, timezone.utc)
        if self.timezone_status == "verified":
            zone = ZoneInfo(self.source_timezone)
            return (datetime.combine(self.report_date, time.min, zone).astimezone(timezone.utc),
                    datetime.combine(self.report_date + timedelta(days=1), time.min, zone).astimezone(timezone.utc))
        return midnight - timedelta(hours=14), midnight + timedelta(days=1, hours=12)


class FuelDailyItem(BaseModel):
    id: UUID
    vehicle_id: UUID
    unit_number: str | None
    fleet_customer_id: UUID
    fleet_name: str
    report_date: date
    source: Literal["motive_vehicle_fuel_performance"]
    source_timezone: str | None
    timezone_status: Literal["unverified", "verified"]
    driving_fuel_gallons: float | None
    idling_fuel_gallons: float | None
    reported_total_fuel_gallons: float | None
    source_distance_miles: float | None
    source_driving_seconds: int | None
    source_idling_seconds: int | None
    source_read_at: datetime
    captured_at: datetime


class FuelDailyPage(BaseModel):
    items: list[FuelDailyItem]
    total: int
    limit: int
    offset: int
    start_date: date
    end_date: date
    imported_start: date | None
    imported_end: date | None
    coverage: Literal["partial"] = "partial"
    date_basis: Literal["source_report_date"] = "source_report_date"
