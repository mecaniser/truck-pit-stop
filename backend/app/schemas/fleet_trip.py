"""Trip read contract and strict operator import validation."""
from datetime import date, datetime, timedelta, timezone
from typing import Literal
from uuid import UUID
import re
import math
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def explicit_timestamp(value):
    if value is not None and not isinstance(value, (str, datetime)):
        raise ValueError("Explicit timestamp required")
    return value


class TripStop(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    location_label: str = Field(min_length=1, max_length=500)
    arrived_at: datetime | None = None
    departed_at: datetime | None = None
    idle_seconds: int | None = Field(default=None, ge=0, strict=True)

    _explicit = field_validator("arrived_at", "departed_at", mode="before")(explicit_timestamp)

    @field_validator("arrived_at", "departed_at")
    @classmethod
    def aware(cls, value):
        if value is None:
            return value
        if value.tzinfo is None:
            raise ValueError("Explicit timezone required")
        return value.astimezone(timezone.utc)

    @model_validator(mode="after")
    def chronological(self):
        if self.arrived_at is None or self.departed_at is None:
            return self
        seconds = (self.departed_at - self.arrived_at).total_seconds()
        if seconds < 0 or (self.idle_seconds is not None and self.idle_seconds > seconds):
            raise ValueError("Invalid stop interval")
        return self


class TripMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    fuel_used_gallons: float | None = Field(default=None, ge=0, le=100000)
    idle_seconds: int | None = Field(default=None, ge=0, strict=True)
    fuel_start_percent: float | None = Field(default=None, ge=0, le=100)
    fuel_end_percent: float | None = Field(default=None, ge=0, le=100)
    estimate_baseline_mpg: float | None = Field(default=None, gt=0, le=100)
    estimate_baseline_captured_at: datetime | None = None
    estimate_baseline_period: Literal["last_30_days"] | None = None

    @field_validator("fuel_used_gallons", "fuel_start_percent", "fuel_end_percent", "estimate_baseline_mpg", mode="before")
    @classmethod
    def no_bool(cls, value):
        if isinstance(value, bool):
            raise ValueError("Measurement must be numeric")
        return value

    _explicit = field_validator("estimate_baseline_captured_at", mode="before")(explicit_timestamp)

    @field_validator("estimate_baseline_captured_at")
    @classmethod
    def aware(cls, value):
        if value is not None and value.tzinfo is None:
            raise ValueError("Explicit timezone required")
        return value.astimezone(timezone.utc) if value is not None else None

    @model_validator(mode="after")
    def baseline_complete(self):
        values = (self.estimate_baseline_mpg, self.estimate_baseline_captured_at, self.estimate_baseline_period)
        if any(value is not None for value in values) and not all(value is not None for value in values):
            raise ValueError("Complete frozen MPG baseline required")
        return self


class TripMetricsRead(TripMetrics):
    trip_mpg: float | None = None
    estimated_fuel_gallons: float | None = None


class TripImport(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, allow_inf_nan=False)
    vin: str
    unit: str = Field(min_length=1, max_length=120)
    source_read_at: datetime
    provider_vehicle_id: str = Field(min_length=1, max_length=120)
    started_at: datetime
    ended_at: datetime
    origin_label: str = Field(min_length=1, max_length=500)
    destination_label: str = Field(min_length=1, max_length=500)
    distance_miles: float = Field(ge=0, le=100000)
    driving_seconds: int = Field(ge=0, le=2678400, strict=True)
    stops: list[TripStop] | None = Field(default=None, max_length=100)
    metrics: TripMetrics | None = None
    timestamp_precision: Literal["second", "minute"] = "second"

    @field_validator("vin")
    @classmethod
    def valid_vin(cls, value):
        value = value.upper()
        if not re.fullmatch(r"[A-HJ-NPR-Z0-9]{17}", value):
            raise ValueError("Verified 17-character VIN required")
        return value

    @field_validator("distance_miles", mode="before")
    @classmethod
    def no_bool(cls, value):
        if isinstance(value, bool):
            raise ValueError("Distance must be numeric")
        return value

    _explicit = field_validator("started_at", "ended_at", "source_read_at", mode="before")(explicit_timestamp)

    @field_validator("started_at", "ended_at", "source_read_at")
    @classmethod
    def aware(cls, value):
        if value is None:
            return value
        if value.tzinfo is None:
            raise ValueError("Explicit timezone required")
        return value.astimezone(timezone.utc)

    @model_validator(mode="after")
    def completed(self):
        duration = (self.ended_at - self.started_at).total_seconds()
        minute = self.timestamp_precision == "minute"
        if minute and any(value.second or value.microsecond for value in (self.started_at, self.ended_at)):
            raise ValueError("Minute timestamps must be minute aligned")
        limit = duration + (59 if minute else 0)
        upper = self.ended_at + timedelta(seconds=60 if minute else 0)
        invalid_interval = duration < 0 or (duration == 0 and (not minute or self.driving_seconds <= 0))
        if invalid_interval or self.driving_seconds > limit or upper > self.source_read_at:
            raise ValueError("Completed trip with valid driving duration required")
        if self.metrics:
            for denominator in (self.metrics.fuel_used_gallons, self.metrics.estimate_baseline_mpg):
                if denominator is not None and denominator > 0 and not math.isfinite(self.distance_miles / denominator):
                    raise ValueError("Trip metrics produce a nonfinite derived measurement")
            if self.metrics.idle_seconds is not None and self.metrics.idle_seconds > limit:
                raise ValueError("Idle time exceeds trip duration")
            baseline_time = self.metrics.estimate_baseline_captured_at
            if baseline_time is not None and not self.source_read_at - timedelta(days=30) <= baseline_time <= self.source_read_at:
                raise ValueError("Baseline must be captured within 30 days before the source read")
        previous = self.started_at
        for stop in self.stops or []:
            if (stop.arrived_at is not None and not previous <= stop.arrived_at <= self.ended_at) or (stop.departed_at is not None and not previous <= stop.departed_at <= self.ended_at):
                raise ValueError("Stops must be ordered inside the trip")
            previous = stop.departed_at or stop.arrived_at or previous
        return self


class TripItem(BaseModel):
    id: UUID
    vehicle_id: UUID
    unit_number: str | None
    fleet_customer_id: UUID
    fleet_name: str
    started_at: datetime
    ended_at: datetime
    origin_label: str
    destination_label: str
    distance_miles: float
    driving_seconds: int
    stops: list[TripStop] | None
    captured_at: datetime
    metrics: TripMetricsRead | None = None
    source: Literal["motive_dashboard_manual"]
    timestamp_precision: Literal["second", "minute"] = "second"


class TripSummary(BaseModel):
    truck_count: int
    coverage: Literal["partial"] = "partial"
    trip_count: int
    distance_miles: float
    driving_seconds: int


class TripPage(BaseModel):
    items: list[TripItem]
    summary: TripSummary
    total: int
    limit: int
    offset: int
    timezone: str
    start_date: date
    end_date: date
