"""DB133 dedicated pricing commands. Generic customer writes never accept these."""
from decimal import Decimal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, field_validator


class CustomerPricingWrite(BaseModel):
    model_config = ConfigDict(extra='forbid')
    expected_version: int = Field(ge=0, strict=True)
    labor_rate: Decimal | None = Field(..., gt=0, max_digits=10, decimal_places=2, allow_inf_nan=False)
    parts_matrix_id: UUID | None
    reason: str = Field(min_length=3, max_length=500)

    @field_validator('labor_rate')
    @classmethod
    def finite_positive_cents(cls, value):
        if value is not None and (not value.is_finite() or value <= 0 or value > Decimal('99999999.99') or value != value.quantize(Decimal('.01'))):
            raise ValueError('Labor rate must be positive, finite and have at most two decimal places')
        return value

    @field_validator('reason', mode='before')
    @classmethod
    def trim_reason(cls, value):
        return value.strip() if isinstance(value, str) else value
