"""Staff schedule wall times are resolved by the server, never the browser zone."""
from datetime import datetime
import re
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StrictInt, field_validator, model_validator


class RepairOrderScheduleUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_updated_at: AwareDatetime
    timezone: str = Field(min_length=1, max_length=100)
    scheduled_start_local: str | None
    promised_finish_local: str | None
    scheduled_start_fold: StrictInt | None = Field(default=None, ge=0, le=1)
    promised_finish_fold: StrictInt | None = Field(default=None, ge=0, le=1)

    @field_validator("scheduled_start_local", "promised_finish_local")
    @classmethod
    def exact_wall_time(cls, value):
        if value is not None:
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}", value, flags=re.ASCII):
                raise ValueError("Use YYYY-MM-DDTHH:mm, without seconds or a timezone offset")
            datetime.strptime(value, "%Y-%m-%dT%H:%M")
        return value

    @model_validator(mode="after")
    def fold_requires_date(self):
        for name in ("scheduled_start", "promised_finish"):
            if getattr(self, name + "_fold") is not None and getattr(self, name + "_local") is None:
                raise ValueError(f"{name}_fold requires {name}_local")
        return self


class RepairOrderScheduleResponse(BaseModel):
    id: UUID
    timezone: str
    scheduled_start_at: datetime | None
    promised_finish_at: datetime | None
    scheduled_start_local: str | None
    promised_finish_local: str | None
    scheduled_start_fold: int | None
    promised_finish_fold: int | None
    updated_at: datetime
    is_overdue: bool
    can_edit: bool
