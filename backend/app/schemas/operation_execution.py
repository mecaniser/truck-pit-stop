from datetime import datetime
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, Field

class OperationVersion(BaseModel):
    expected_version: int = Field(ge=0)

class OperationAssignment(OperationVersion):
    mechanic_id: UUID | None

class OperationCompletion(OperationVersion):
    is_completed: bool

class OperationTimerStop(OperationVersion):
    session_id: UUID

class OperationActor(BaseModel):
    id: UUID | None
    name: str | None

class OperationSession(BaseModel):
    id: UUID
    mechanic_id: UUID
    mechanic_name: str
    started_at: datetime

class OperationItem(BaseModel):
    labor_id: UUID
    description: str
    mechanic_id: UUID | None
    mechanic_name: str | None
    status: Literal['pending', 'completed'] | None
    version: int
    completed_at: datetime | None
    completed_by: OperationActor | None
    tracked_seconds: int | None
    active_session: OperationSession | None
    required_tasks_remaining: int
    can_assign: bool
    can_complete: bool
    can_reopen: bool
    can_start_timer: bool
    can_stop_timer: bool

class OperationSummary(BaseModel):
    tracked: int
    completed: int
    remaining: int
    legacy_untracked: int

class OperationPage(BaseModel):
    items: list[OperationItem]
    summary: OperationSummary
    order_status: str
    is_order_lead: bool
