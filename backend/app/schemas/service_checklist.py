from datetime import datetime
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    field_validator,
)


class ChecklistTemplateInputItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: UUID | None = None
    label: str = Field(min_length=1, max_length=300, strict=True)
    required: StrictBool = True

    @field_validator("label", mode="before")
    @classmethod
    def trim_label(cls, value):
        return value.strip() if isinstance(value, str) else value


class ChecklistTemplateUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: StrictInt = Field(ge=0)
    items: list[ChecklistTemplateInputItem] = Field(max_length=50)

    @field_validator("items")
    @classmethod
    def unique_ids(cls, items):
        ids = [item.id for item in items if item.id is not None]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate checklist task IDs")
        return items


class ChecklistTemplateItem(BaseModel):
    id: UUID
    label: str
    required: bool


class ChecklistTemplateResponse(BaseModel):
    service_id: UUID
    version: int
    items: list[ChecklistTemplateItem]


class ChecklistTaskUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    is_completed: StrictBool
    expected_version: StrictInt = Field(ge=1)


class ChecklistActor(BaseModel):
    id: UUID
    name: str


class ChecklistTaskResponse(BaseModel):
    id: UUID
    labor_id: UUID
    service_name: str
    label: str
    required: bool
    position: int
    is_completed: bool
    completed_at: datetime | None
    completed_by: ChecklistActor | None
    version: int


class ChecklistSummary(BaseModel):
    total: int
    completed: int
    required: int
    required_remaining: int


class ChecklistPage(BaseModel):
    items: list[ChecklistTaskResponse]
    total: int
    skip: int
    limit: int
    summary: ChecklistSummary
    can_update: bool


class ChecklistTaskUpdateResponse(ChecklistTaskResponse):
    summary: ChecklistSummary
    can_update: bool
