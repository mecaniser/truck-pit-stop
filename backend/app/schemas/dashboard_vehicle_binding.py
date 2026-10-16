"""Internal reviewed-binding inputs; never accepted by public manual capture."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.fleet_telemetry import TelemetryCapture


class BindingManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    vehicle_id: UUID
    fleet_customer_id: UUID
    fleet_membership_id: UUID
    source_company_id: str = Field(min_length=1, max_length=120)
    source_company_label: str = Field(min_length=1, max_length=255)
    provider_vehicle_id: str = Field(pattern=r"^[0-9]{1,120}$")
    placeholder_vin: str = Field(pattern=r"^PENDING-[A-Z0-9-]{1,9}$", max_length=17)
    effective_to: datetime | None = None
    review_note: str = Field(min_length=10, max_length=1000)
    source_evidence_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_evidence_read_at: datetime
    source_vin_state: Literal["not_displayed", "explicitly_empty"]

    @field_validator("effective_to", "source_evidence_read_at")
    @classmethod
    def aware_time(cls, value):
        if value is not None and value.tzinfo is None:
            raise ValueError("Explicit binding expiry timezone required")
        return value


class BoundTelemetryCapture(TelemetryCapture):
    vin: None = None
    dashboard_binding_id: UUID
    source_company_id: str = Field(min_length=1, max_length=120)
    source_read_at: datetime
    source_vin_state: Literal["not_displayed", "explicitly_empty"]

    @field_validator("vin")
    @classmethod
    def normalize_vin(cls, value):
        return value

    @model_validator(mode="after")
    def binding_proof(self):
        if (
            self.source_vin_state not in {"not_displayed", "explicitly_empty"}
            or self.source_read_at.tzinfo is None
        ):
            raise ValueError("Verified source VIN state and timezone required")
        return self
