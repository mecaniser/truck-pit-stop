from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
from uuid import UUID
from decimal import Decimal
from app.db.models.repair_order import RepairOrderStatus


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


