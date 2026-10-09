"""Bounded Motive driver observations; source labels are not inferred risk ratings."""

from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class DriverSourceModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid", str_strip_whitespace=True, revalidate_instances="always"
    )

    @field_validator("*", mode="after")
    @classmethod
    def safe_text(cls, value):
        values = value if isinstance(value, list) else [value]
        for item in values:
            if isinstance(item, str) and (
                "\x00" in item or any(0xD800 <= ord(char) <= 0xDFFF for char in item)
            ):
                raise ValueError("Unsupported text character")
        return value


class DriverBehavior(DriverSourceModel):
    behavior: str = Field(min_length=1, max_length=160)
    score_impact: float | None = Field(
        default=None, ge=-100, le=100, allow_inf_nan=False, strict=True
    )


class DriverScorePoint(DriverSourceModel):
    period_text: str = Field(min_length=1, max_length=120)
    score: float = Field(ge=0, le=100, allow_inf_nan=False, strict=True)


class DriverSafety(DriverSourceModel):
    score: float | None = Field(
        default=None, ge=0, le=100, allow_inf_nan=False, strict=True
    )
    band: Literal["red", "yellow", "green", "unknown"] = "unknown"
    band_label: str | None = Field(default=None, max_length=120)
    period_text: str | None = Field(default=None, max_length=160)
    coaching_label: str | None = Field(default=None, max_length=120)
    top_behaviors: list[DriverBehavior] = Field(default_factory=list, max_length=30)
    history: list[DriverScorePoint] = Field(default_factory=list, max_length=104)

    @model_validator(mode="after")
    def provider_band(self):
        if self.band != "unknown" and not self.band_label:
            raise ValueError("Provider risk label required for a colored band")
        if self.band_label and self.band_label.casefold() == "coaching":
            raise ValueError("Coaching chart annotation is not a risk band")
        return self


class DriverMetric(DriverSourceModel):
    label: str = Field(min_length=1, max_length=120)
    value: str = Field(min_length=1, max_length=120)
    unit: str | None = Field(default=None, max_length=40)


class DriverFuel(DriverSourceModel):
    period_text: str | None = Field(default=None, max_length=160)
    utilization_percent: float | None = Field(
        default=None, ge=0, le=100, allow_inf_nan=False, strict=True
    )
    active_time_text: str | None = Field(default=None, max_length=120)
    idle_time_text: str | None = Field(default=None, max_length=120)
    metrics: list[DriverMetric] = Field(default_factory=list, max_length=30)


class DriverCoaching(DriverSourceModel):
    status_label: str | None = Field(default=None, max_length=160)
    open_count: int | None = Field(default=None, ge=0, le=100000, strict=True)
    last_coached_text: str | None = Field(default=None, max_length=120)


class DriverRecentEvent(DriverSourceModel):
    occurred_at_text: str | None = Field(default=None, max_length=120)
    behavior: str = Field(min_length=1, max_length=160)
    severity: str | None = Field(default=None, max_length=120)
    status: str | None = Field(default=None, max_length=120)
    vehicle_label: str | None = Field(default=None, max_length=120)
    location: str | None = Field(default=None, max_length=255)


SectionState = Literal["available", "unavailable", "empty"]


class DriverSections(DriverSourceModel):
    safety: SectionState = "unavailable"
    fuel: SectionState = "unavailable"
    coaching: SectionState = "unavailable"
    recent_events: SectionState = "unavailable"


class DriverRecordContent(DriverSourceModel):
    safety: DriverSafety = Field(default_factory=DriverSafety)
    fuel: DriverFuel = Field(default_factory=DriverFuel)
    coaching: DriverCoaching = Field(default_factory=DriverCoaching)
    recent_events: list[DriverRecentEvent] = Field(default_factory=list, max_length=100)
    sections: DriverSections = Field(default_factory=DriverSections)
    coverage: Literal["partial", "complete"] = "partial"
    unavailable_reasons: list[str] = Field(default_factory=list, max_length=20)
    source_timezone: str | None = Field(default=None, max_length=120)

    @field_validator("unavailable_reasons")
    @classmethod
    def bounded_reasons(cls, value):
        if any(not reason or len(reason) > 255 for reason in value):
            raise ValueError("Unavailable reasons must be 1-255 characters")
        return value

    @model_validator(mode="after")
    def section_coverage(self):
        if (
            self.coverage == "complete"
            and "unavailable" in self.sections.model_dump().values()
        ):
            raise ValueError("Complete capture cannot contain unavailable sections")
        for name in ("safety", "fuel", "coaching"):
            if getattr(self.sections, name) != "available":
                value = getattr(self, name)
                if value.model_dump() != type(value)().model_dump():
                    raise ValueError(f"Unavailable/empty {name} cannot carry readings")
        if self.sections.recent_events != "available" and self.recent_events:
            raise ValueError("Unavailable/empty events cannot carry rows")
        return self


class DriverRecordCapture(DriverRecordContent):
    client_request_id: UUID
    vin: str = Field(pattern=r"^[A-HJ-NPR-Z0-9]{17}$")
    provider_vehicle_id: str = Field(min_length=1, max_length=120)
    provider_driver_id: str = Field(min_length=1, max_length=120)
    driver_name: str = Field(min_length=1, max_length=160)
    source_company_id: str = Field(min_length=1, max_length=120)
    source_company_label: str = Field(min_length=1, max_length=255)
    company_verified_before: Literal[True]
    company_verified_after: Literal[True]
    assignment_verified_before: Literal[True]
    assignment_verified_after: Literal[True]
    source_read_at: datetime

    @model_validator(mode="before")
    @classmethod
    def verified_flags(cls, value):
        if isinstance(value, dict) and any(
            value.get(name) is not True
            for name in (
                "company_verified_before",
                "company_verified_after",
                "assignment_verified_before",
                "assignment_verified_after",
            )
        ):
            raise ValueError(
                "Explicit verified company and assignment evidence required"
            )
        return value

    @field_validator("source_read_at", mode="before")
    @classmethod
    def explicit_time_input(cls, value):
        if not isinstance(value, (str, datetime)):
            raise ValueError("Explicit source read datetime required")  # noqa: TRY004 - Pydantic validation error
        return value

    @field_validator("source_read_at")
    @classmethod
    def explicit_time(cls, value):
        if value.tzinfo is None:
            raise ValueError("Source read timezone required")
        return value.astimezone(timezone.utc)


class DriverRecordSummary(BaseModel):
    capture_id: UUID
    provider_driver_id: str
    driver_name: str
    safety_score: float | None = None
    safety_band: Literal["red", "yellow", "green", "unknown"] = "unknown"
    safety_band_label: str | None = None
    safety_period_text: str | None = None
    last_checked_at: datetime
    coverage: Literal["partial", "complete"]
    stale: bool = False


class DriverRecordDetail(DriverRecordSummary, DriverRecordContent):
    pass


class TruckDriverRecordRead(BaseModel):
    vehicle_id: UUID
    source: Literal["motive_dashboard"] = "motive_dashboard"
    availability: Literal["unknown", "available", "assignment_unverified"] = "unknown"
    record: DriverRecordDetail | None = None
