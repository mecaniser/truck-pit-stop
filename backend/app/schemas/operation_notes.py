"""Append-only shop notes tied to one exact repair-order operation."""
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, StrictStr, field_validator


class OperationNoteCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    body: StrictStr

    @field_validator("body")
    @classmethod
    def normalize_body(cls, value: str) -> str:
        value = value.strip()
        if not 1 <= len(value) <= 4000:
            raise ValueError("Enter a note between 1 and 4000 characters.")
        return value


class OperationNoteItem(BaseModel):
    id: UUID
    labor_id: UUID
    body: str
    actor_user_id: UUID | None
    actor_name: str
    created_at: datetime


class OperationNotesPage(BaseModel):
    items: list[OperationNoteItem]
    can_add: bool
    read_only_reason: str | None
