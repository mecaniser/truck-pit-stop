from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from uuid import UUID


class VehicleBase(BaseModel):
    vin: Optional[str] = None
    make: str
    model: str
    year: Optional[int] = None
    license_plate: Optional[str] = None
    color: Optional[str] = None
    mileage: Optional[int] = None
    notes: Optional[str] = None


class VehicleCreate(VehicleBase):
    customer_id: UUID


class VehicleUpdate(BaseModel):
    vin: Optional[str] = None
    make: Optional[str] = None
    model: Optional[str] = None
    year: Optional[int] = None
    license_plate: Optional[str] = None
    color: Optional[str] = None
    mileage: Optional[int] = None
    notes: Optional[str] = None


class VehicleResponse(VehicleBase):
    id: UUID
    tenant_id: UUID
    customer_id: UUID
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True

