"""Reduced staff-only technical recommendation projection (DB-099)."""
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from app.db.models.recommended_service import RecommendedServicePriority
from app.db.models.repair_order import RepairOrderStatus
from app.schemas.recommendation_conversion import RecommendationConversionResponse


class RecommendedWorkVehicle(BaseModel):
    id: UUID
    unit_number: str | None
    year: int | None
    make: str | None
    model: str | None


class RecommendedWorkSourceOrder(BaseModel):
    id: UUID
    order_number: str
    status: RepairOrderStatus
    created_at: datetime


class RecommendedWorkItem(BaseModel):
    conversion: RecommendationConversionResponse | None = None
    id: UUID
    description: str
    priority: RecommendedServicePriority
    created_at: datetime
    vehicle: RecommendedWorkVehicle
    source_order: RecommendedWorkSourceOrder


class RecommendedWorkPage(BaseModel):
    items: list[RecommendedWorkItem]
    total: int
    skip: int
    limit: int
