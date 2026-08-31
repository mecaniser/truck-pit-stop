from decimal import Decimal, ROUND_HALF_UP
from typing import Literal

from pydantic import BaseModel, Field, field_serializer


class FilteredRepairOrderValueSummary(BaseModel):
    order_count: int = Field(ge=0)
    order_value: Decimal = Field(ge=Decimal("0.00"))
    currency: Literal["USD"] = "USD"
    amount_basis: Literal["repair_order_net"] = "repair_order_net"

    @field_serializer("order_value")
    def serialize_order_value(self, value: Decimal) -> str:
        return str(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
