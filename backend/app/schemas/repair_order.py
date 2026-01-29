from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
from uuid import UUID
from decimal import Decimal
from app.db.models.repair_order import RepairOrderStatus


# --- Parts and labor line items ---


class PartsUsageCreate(BaseModel):
    inventory_id: UUID
    quantity: int
    unit_price: Optional[Decimal] = None  # override; else use inventory selling_price


class PartsUsageResponse(BaseModel):
    id: UUID
    repair_order_id: UUID
    inventory_id: UUID
    inventory_sku: str
    inventory_name: str
    quantity: int
    unit_price: Decimal
    total_price: Decimal
    created_at: datetime

    class Config:
        from_attributes = True


class LaborCreate(BaseModel):
    description: Optional[str] = None
    hours: Decimal
    hourly_rate: Decimal
    mechanic_id: Optional[UUID] = None
    service_code: Optional[str] = None


class LaborUpdate(BaseModel):
    description: Optional[str] = None
    hours: Optional[Decimal] = None
    hourly_rate: Optional[Decimal] = None
    mechanic_id: Optional[UUID] = None
    service_code: Optional[str] = None


class LaborResponse(BaseModel):
    id: UUID
    repair_order_id: UUID
    description: str
    hours: Decimal
    hourly_rate: Decimal
    total_cost: Decimal
    mechanic_id: Optional[UUID] = None
    service_code: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class RepairOrderBase(BaseModel):
    description: Optional[str] = None
    customer_notes: Optional[str] = None
    internal_notes: Optional[str] = None


class RepairOrderCreate(RepairOrderBase):
    customer_id: UUID
    vehicle_id: UUID
    assigned_mechanic_id: Optional[UUID] = None


class RepairOrderUpdate(BaseModel):
    status: Optional[RepairOrderStatus] = None
    description: Optional[str] = None
    customer_notes: Optional[str] = None
    internal_notes: Optional[str] = None
    assigned_mechanic_id: Optional[UUID] = None


class RepairOrderResponse(RepairOrderBase):
    id: UUID
    tenant_id: UUID
    customer_id: UUID
    vehicle_id: UUID
    order_number: str
    status: RepairOrderStatus
    assigned_mechanic_id: Optional[UUID]
    total_parts_cost: Decimal
    total_labor_cost: Decimal
    total_cost: Decimal
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class RepairOrderDetailResponse(RepairOrderResponse):
    parts_usage: List[PartsUsageResponse] = []
    labor_items: List[LaborResponse] = []


