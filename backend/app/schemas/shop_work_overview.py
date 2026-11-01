"""DB-151 read-only task candidates; deliberately no financial amounts."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

SourceId = Literal['repairs', 'schedule', 'inventory', 'purchasing', 'returns', 'cores', 'receivables']


class ShopWorkSource(BaseModel):
    id: SourceId
    state: Literal['ready', 'partial', 'unavailable', 'restricted', 'disabled']
    checked_at: datetime | None = None
    reason: str | None = None
    total: int | None = None
    shown: int = 0
    has_more: bool = False


class ShopWorkDestination(BaseModel):
    kind: Literal['repair_order', 'inventory', 'purchase_order', 'vendor_return', 'core', 'customer_account']
    id: str
    view: str | None = None


class ShopWorkItem(BaseModel):
    id: str
    source: SourceId
    destination: ShopWorkDestination
    title: str
    reason: str
    action_label: str
    status: str
    created_at: datetime | None = None
    due_at: datetime | None = None
    due_kind: Literal['repair_promise', 'repair_start', 'expected_delivery'] | None = None
    evidence: Literal['verified', 'review_required'] = 'verified'
    quantity: int | None = None
    related_repair_order_ids: list[str] = Field(default_factory=list)


class ShopWorkOverview(BaseModel):
    as_of: datetime
    timezone: str | None
    scope: Literal['shop', 'assigned']
    active_jobs: int | None
    sources: list[ShopWorkSource]
    actions: list[ShopWorkItem]
    upcoming: list[ShopWorkItem]
    actions_total: int | None
    upcoming_total: int | None
    has_more_actions: bool
    has_more_upcoming: bool
