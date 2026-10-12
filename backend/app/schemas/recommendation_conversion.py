from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, field_validator
from app.core.work_value_validation import validate_labor_hours
from app.db.models.repair_order import RepairOrderStatus


class RecommendationConvertRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_id: UUID
    hours: Decimal
    hourly_rate: Decimal
    replaces_conversion_id: UUID | None = None

    @field_validator("hours")
    @classmethod
    def valid_hours(cls, value):
        return validate_labor_hours(value)

    @field_validator("hourly_rate")
    @classmethod
    def valid_rate(cls, value):
        try:
            if not value.is_finite() or not Decimal("0") <= value <= Decimal("99999999.99") or value != value.quantize(Decimal("0.01")):
                raise ValueError("Hourly rate must be nonnegative with at most two decimal places")
        except InvalidOperation as exc:
            raise ValueError("Invalid hourly rate") from exc
        return value


class ConversionOrderReference(BaseModel):
    id: UUID
    order_number: str
    available: bool


class ConversionTargetReference(ConversionOrderReference):
    status: RepairOrderStatus


ConversionState = Literal["active", "operation_removed", "target_cancelled", "target_deleted", "superseded"]


class RecommendationConversionResponse(BaseModel):
    id: UUID
    recommendation_id: UUID
    source_order: ConversionOrderReference
    source_description: str
    target_order: ConversionTargetReference
    labor_id: UUID
    state: ConversionState
    created_at: datetime
    can_replace: bool
    can_resolve: bool


class RecommendationSourceResponse(BaseModel):
    conversion_id: UUID
    recommendation_id: UUID
    source_order: ConversionOrderReference
    description: str
    state: ConversionState


class RecommendationConvertResponse(BaseModel):
    conversion: RecommendationConversionResponse
    replayed: bool
    warnings: list[dict] = []
