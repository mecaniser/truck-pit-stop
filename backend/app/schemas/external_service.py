"""Staff-entered historical work; no financial or vehicle telemetry mutations."""
from datetime import date, datetime
from decimal import Decimal
import re
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr, field_validator


class ExternalServiceFields(BaseModel):
    model_config = ConfigDict(extra="forbid")
    provider_name: StrictStr
    service_date: date
    description: StrictStr
    odometer: StrictInt | None = Field(default=None, ge=0, le=99999999)
    reference: StrictStr | None = None
    reported_cost: Decimal | None = Field(default=None, ge=0, le=Decimal("9999999999.99"))

    @field_validator("provider_name", "description", "reference")
    @classmethod
    def text_bounds(cls, value, info):
        if value is None:
            return None
        value = value.strip()
        if info.field_name == "reference" and not value:
            return None
        maximum = {"provider_name": 160, "description": 4000, "reference": 100}[info.field_name]
        if not 1 <= len(value) <= maximum:
            raise ValueError(f"Enter between 1 and {maximum} characters.")
        return value

    @field_validator("service_date", mode="before")
    @classmethod
    def date_only(cls, value):
        if isinstance(value, datetime) or not (isinstance(value, date) or (isinstance(value, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value))):
            raise ValueError("Enter a service date as YYYY-MM-DD.")
        return value

    @field_validator("service_date")
    @classmethod
    def earliest_date(cls, value):
        if value < date(1900, 1, 1):
            raise ValueError("Service date must be on or after January 1, 1900.")
        return value

    @field_validator("reported_cost", mode="before")
    @classmethod
    def finite_cost(cls, value):
        if isinstance(value, bool):
            raise ValueError("Enter a valid reported cost.")
        return value

    @field_validator("reported_cost")
    @classmethod
    def canonical_cost(cls, value):
        if value is None:
            return None
        if not value.is_finite() or value != value.quantize(Decimal("0.01")):
            raise ValueError("Reported cost must have at most two decimal places.")
        return value.quantize(Decimal("0.01"))


class ExternalServiceCreate(ExternalServiceFields):
    request_id: UUID


class ExternalServiceUpdate(ExternalServiceCreate):
    expected_version: StrictInt = Field(ge=1)
    odometer: StrictInt | None = Field(..., ge=0, le=99999999)
    reference: StrictStr | None = Field(...)
    reported_cost: Decimal | None = Field(..., ge=0, le=Decimal("9999999999.99"))


class ExternalServiceRestore(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_id: UUID
    expected_version: StrictInt = Field(ge=1)


class ExternalServiceVoid(ExternalServiceRestore):
    reason: StrictStr

    @field_validator("reason")
    @classmethod
    def reason_bounds(cls, value):
        value = value.strip()
        if not 1 <= len(value) <= 500:
            raise ValueError("Enter a reason between 1 and 500 characters.")
        return value


class ExternalServiceItem(ExternalServiceFields):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    vehicle_id: UUID
    original_vehicle_id: UUID
    source: Literal["external"] = "external"
    currency: Literal["USD"] = "USD"
    version: int
    voided_at: datetime | None
    created_at: datetime
    updated_at: datetime
    created_by_user_id: UUID
    created_by_name: str
    updated_by_user_id: UUID
    updated_by_name: str

    @field_validator("created_at", "updated_at", "voided_at")
    @classmethod
    def aware_timestamp(cls, value):
        from datetime import UTC
        return value.replace(tzinfo=UTC) if value is not None and value.tzinfo is None else value


class ExternalServicePage(BaseModel):
    items: list[ExternalServiceItem]
    total: int
    has_more: bool


class ExternalServiceMutation(BaseModel):
    record: ExternalServiceItem
    replayed: bool


class ExternalServiceHistoryItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    record_id: UUID
    version: int
    action: Literal["create", "update", "void", "restore"]
    actor_user_id: UUID
    actor_name: str
    created_at: datetime
    reason: str | None
    snapshot: ExternalServiceItem


class ExternalServiceHistoryPage(BaseModel):
    items: list[ExternalServiceHistoryItem]
    total: int
    has_more: bool
