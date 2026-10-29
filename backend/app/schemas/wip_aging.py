"""Read-only Shop Work aging projection. No financial values or source writers."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

WipCategory = Literal['approval', 'parts', 'technician', 'review', 'other_hold', 'active', 'preparation']
WipCategoryFilter = Literal['all', 'approval', 'parts', 'technician', 'review', 'other_hold', 'active', 'preparation']
WipTiming = Literal['all', 'known', 'unknown']
WipSort = Literal['priority', 'oldest_wait', 'oldest_order']
WipReason = Literal[
    'waiting_for_parts', 'approval_hold', 'awaiting_customer_decision',
    'awaiting_acknowledgment', 'ready_to_start', 'technician_timing_unknown',
    'awaiting_quality_review', 'need_more_info', 'technician_switched',
    'other_hold', 'work_in_progress', 'prepare_estimate', 'revise_estimate',
    'quote_not_sent', 'quote_expired', 'quote_evidence_unknown',
]


class WipClock(BaseModel):
    state: Literal['known', 'unknown', 'not_applicable']
    since: datetime | None = None
    seconds: int | None = Field(default=None, ge=0)
    issue: Literal['missing_timestamp', 'future_timestamp', 'inconsistent_evidence'] | None = None


class WipAgingRow(BaseModel):
    id: str
    order_number: str
    status: str
    customer_name: str
    vehicle_info: str
    vehicle_unit_number: str | None
    category: WipCategory
    reason: WipReason
    hold_reason: str | None
    assignment: Literal['assigned', 'unassigned', 'unknown']
    technician_names: list[str]
    order_age: WipClock
    current_wait: WipClock
    promised_finish_at: datetime | None
    overdue_seconds: int | None
    is_overdue: bool
    action_lane: Literal['needs_action', 'on_floor']


class WipFilters(BaseModel):
    search: str = ''
    category: WipCategoryFilter = 'all'
    overdue_only: bool = False
    timing: WipTiming = 'all'
    sort: WipSort = 'priority'


class WipSummary(BaseModel):
    total_jobs: int
    category_counts: dict[WipCategory, int]
    overdue_jobs: int
    unknown_wait_jobs: int


class WipAgingResponse(BaseModel):
    as_of: datetime
    timezone: str | None
    scope: Literal['shop', 'assigned']
    filters: WipFilters
    summary: WipSummary
    filtered_total: int
    offset: int
    limit: int
    has_more: bool
    items: list[WipAgingRow]
