"""Strict metadata-only C3 inputs and privacy-limited projections."""

from datetime import date, datetime
import re
from typing import Literal
from uuid import UUID
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictInt,
    StrictStr,
    field_validator,
    model_validator,
)

Priority = Literal["urgent", "soon", "monitor"]
State = Literal["open", "resolved", "dismissed"]


class StrictInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class IssueCreate(StrictInput):
    request_id: UUID
    description: StrictStr
    priority: Priority = "soon"
    responsible_user_id: UUID | None = None
    follow_up_on: date | None = None

    @field_validator("description")
    @classmethod
    def description_text(cls, value):
        value = value.strip()
        if not 1 <= len(value) <= 2000:
            raise ValueError("Enter 1 to 2000 characters.")
        return value

    @field_validator("follow_up_on", mode="before")
    @classmethod
    def date_only(cls, value):
        if value is not None and (
            isinstance(value, datetime)
            or not (
                isinstance(value, date)
                or isinstance(value, str)
                and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value)
            )
        ):
            raise ValueError("Enter a date as YYYY-MM-DD.")
        return value


class IssueEdit(StrictInput):
    request_id: UUID
    expected_version: StrictInt = Field(ge=1)
    description: StrictStr | None = None
    priority: Priority | None = None
    responsible_user_id: UUID | None = None
    follow_up_on: date | None = None
    _date_only = field_validator("follow_up_on", mode="before")(
        IssueCreate.date_only.__func__
    )

    @model_validator(mode="after")
    def edited_fields(self):
        fields = self.model_fields_set - {"request_id", "expected_version"}
        if not fields:
            raise ValueError("Change at least one field.")
        for field in fields & {"description", "priority"}:
            if getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null.")
        if "description" in fields:
            self.description = IssueCreate.description_text(self.description)
        return self


class IssueVersioned(StrictInput):
    request_id: UUID
    expected_version: StrictInt = Field(ge=1)


class IssueReason(IssueVersioned):
    reason: StrictStr

    @field_validator("reason")
    @classmethod
    def reason_text(cls, value):
        value = value.strip()
        if not 1 <= len(value) <= 1000:
            raise ValueError("Enter a reason of 1 to 1000 characters.")
        return value


class IssueStateChange(IssueReason):
    state: State


class IssueLinkCreate(IssueVersioned):
    target_order_id: UUID


class IssueOwner(BaseModel):
    id: UUID
    display_name: str
    active: bool


class IssueLink(BaseModel):
    id: UUID
    target_order_id: UUID | None
    order_number: str | None
    availability: Literal["available", "unavailable"]
    created_at: datetime


class IssueCapabilities(BaseModel):
    can_edit: bool
    can_change_state: bool
    can_link_context: bool
    can_end_link: bool


class Issue(BaseModel):
    id: UUID
    vehicle_id: UUID
    description: str
    priority: Priority
    state: State
    version: int
    responsible_user: IssueOwner | None
    follow_up_on: date | None
    follow_up_state: Literal[
        "unscheduled", "upcoming", "today", "overdue", "closed", "unknown"
    ]
    created_at: datetime
    updated_at: datetime
    state_changed_at: datetime | None
    state_reason: str | None
    current_link: IssueLink | None
    capabilities: IssueCapabilities


class IssuePage(BaseModel):
    items: list[Issue]
    total: int
    skip: int
    limit: int
    has_more: bool
    as_of: datetime
    timezone: str | None


class IssueMutation(BaseModel):
    issue: Issue
    replayed: bool
