"""Staff hold is an operational sub-state, independent of timer start/resume."""
from datetime import datetime
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator

from app.db.models.repair_order import RepairOrderStatus


class StaffReleaseHoldRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_updated_at: AwareDatetime


class StaffHoldRequest(StaffReleaseHoldRequest):
    reason: str = Field(min_length=1, max_length=100)

    @field_validator("reason", mode="before")
    @classmethod
    def trim_reason(cls, value):
        return value.strip() if isinstance(value, str) else value


class StaffHoldResponse(BaseModel):
    id: UUID
    status: RepairOrderStatus
    hold_reason: str | None
    held_at: datetime | None
    updated_at: datetime
    stopped_sessions_count: int
