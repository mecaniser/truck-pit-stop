"""Read-only imported invoice evidence; never a native collectible balance."""
from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_serializer


class ImportedBillingResponse(BaseModel):
    source: Literal["easy_truck_shop_import"] = "easy_truck_shop_import"
    invoice_id: UUID | None = None
    invoice_number: str | None = None
    total_amount: Decimal | None = None
    recorded_completed_amount: Decimal | None = None
    recorded_remaining_amount: Decimal | None = None
    payment_status: Literal["paid", "partially_paid", "unpaid", "unverified"] = "unverified"
    evidence_basis: Literal["imported_records", "ets_source_snapshot"] = "imported_records"
    reconciliation_status: Literal["not_checked"] = "not_checked"
    observed_at: datetime | None = None
    review_required: bool = True
    review_reasons: list[str] = Field(default_factory=list)

    @field_serializer("total_amount", "recorded_completed_amount", "recorded_remaining_amount")
    def serialize_money(self, value: Decimal | None) -> str | None:
        return format(value, ".2f") if value is not None else None
