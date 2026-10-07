"""Honest source-observation contract; unknown event time is not capture time."""

from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class DiagnosticCode(BaseModel):
    model_config = ConfigDict(
        extra="forbid", str_strip_whitespace=True, revalidate_instances="always"
    )
    code: str | None = Field(default=None, max_length=120)
    spn: str | None = Field(default=None, max_length=120)
    fmi: str | None = Field(default=None, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    severity: str | None = Field(default=None, max_length=120)
    network: str | None = Field(default=None, max_length=120)
    source_address: str | None = Field(default=None, max_length=255)
    source_status: Literal["Current fault codes"] = "Current fault codes"
    provider_fault_id: None = None
    occurrence_count: int | None = Field(default=None, ge=0, strict=True)
    first_detected_text: str | None = Field(default=None, max_length=120)
    last_observed_text: str | None = Field(default=None, max_length=120)
    first_detected_at: None = None
    last_observed_at: None = None
    timestamp_precision: Literal["unknown"] = "unknown"
    timezone_basis: Literal["unverified"] = "unverified"

    @model_validator(mode="after")
    def identifying_content(self):
        if not any((self.code, self.spn, self.description)):
            raise ValueError("Source code or description required")
        return self


class DiagnosticCapture(BaseModel):
    model_config = ConfigDict(
        extra="forbid", str_strip_whitespace=True, revalidate_instances="always"
    )
    client_request_id: UUID
    vin: str = Field(pattern=r"^[A-HJ-NPR-Z0-9]{17}$")
    provider_vehicle_id: str = Field(min_length=1, max_length=120)
    source_company_id: str = Field(min_length=1, max_length=120)
    source_company_label: str = Field(min_length=1, max_length=255)
    company_verified_before: Literal[True]
    company_verified_after: Literal[True]
    source_read_at: datetime
    coverage: Literal["complete"] = "complete"
    explicit_empty: bool = Field(strict=True)
    source_scope: Literal["Current fault codes"] = "Current fault codes"
    count_before: int = Field(ge=0, le=200, strict=True)
    count_after: int = Field(ge=0, le=200, strict=True)
    codes: list[DiagnosticCode] = Field(max_length=200)

    @field_validator("source_read_at")
    @classmethod
    def explicit_time(cls, value):
        if value.tzinfo is None:
            raise ValueError("Source read timezone required")
        return value.astimezone(timezone.utc)

    @model_validator(mode="after")
    def complete_scope(self):
        if self.count_before != self.count_after or self.count_before != len(
            self.codes
        ):
            raise ValueError("Source count changed or detail capture incomplete")
        if self.explicit_empty != (len(self.codes) == 0):
            raise ValueError("Explicit source zero required for empty observation")
        identities = [
            (
                code.code,
                code.spn,
                code.fmi,
                code.network,
                code.source_address,
                code.description,
            )
            for code in self.codes
        ]
        if len(set(identities)) != len(identities):
            raise ValueError("Duplicate diagnostic cards")
        return self


class DiagnosticObservationRead(BaseModel):
    capture_id: UUID
    last_checked_at: datetime
    coverage: Literal["complete"]
    explicit_empty: bool
    source_scope: Literal["Current fault codes"]
    codes: list[DiagnosticCode]


class TruckDiagnosticsRead(BaseModel):
    vehicle_id: UUID
    source: Literal["motive_dashboard"] = "motive_dashboard"
    capture_id: UUID | None = None
    last_checked_at: datetime | None = None
    coverage: Literal["unknown", "partial", "complete"] = "unknown"
    explicit_empty: bool | None = None
    source_scope: Literal["Current fault codes"] = "Current fault codes"
    codes: list[DiagnosticCode] = Field(default_factory=list)
    previously_reported: list[DiagnosticObservationRead] = Field(default_factory=list)
