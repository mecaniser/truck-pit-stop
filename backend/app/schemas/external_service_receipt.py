"""Metadata-only receipt API. Private bytes and hashes never enter schemas."""
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr, field_validator


class ReceiptUpload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_id: UUID
    expected_record_version: StrictInt = Field(ge=1)


class ReceiptRestore(ReceiptUpload):
    expected_version: StrictInt = Field(ge=1)


class ReceiptRemove(ReceiptRestore):
    reason: StrictStr

    @field_validator("reason")
    @classmethod
    def reason_bounds(cls, value):
        value = value.strip()
        if not 1 <= len(value) <= 500:
            raise ValueError("Enter a reason between 1 and 500 characters.")
        return value


class ReceiptItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    record_id: UUID
    vehicle_id: UUID
    uploaded_vehicle_id: UUID
    filename: str
    media_type: Literal["application/pdf", "image/jpeg", "image/png"]
    size_bytes: int
    version: int
    removed_at: datetime | None
    created_at: datetime
    updated_at: datetime
    created_by_user_id: UUID
    created_by_name: str
    updated_by_user_id: UUID
    updated_by_name: str

    @field_validator("created_at", "updated_at", "removed_at")
    @classmethod
    def aware_timestamp(cls, value):
        return value.replace(tzinfo=UTC) if value is not None and value.tzinfo is None else value


class ReceiptPage(BaseModel):
    items: list[ReceiptItem]
    total: int
    retained_count: int
    retained_bytes: int
    max_files: int = 10
    max_file_bytes: int = 5242880
    max_total_bytes: int = 52428800
    record_version: int
    record_voided_at: datetime | None


class ReceiptMutation(BaseModel):
    receipt: ReceiptItem
    replayed: bool
    record_version: int
    record_voided_at: datetime | None


class ReceiptHistoryItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    receipt_id: UUID
    record_id: UUID
    version: int
    action: Literal["upload", "remove", "restore"]
    actor_user_id: UUID
    actor_name: str
    created_at: datetime
    reason: str | None
    snapshot: ReceiptItem


class ReceiptHistoryPage(BaseModel):
    items: list[ReceiptHistoryItem]
    total: int
    has_more: bool
