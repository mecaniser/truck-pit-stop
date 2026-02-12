from pydantic import BaseModel, Field
from typing import Optional, List, TYPE_CHECKING
from datetime import datetime
from uuid import UUID
from decimal import Decimal

if TYPE_CHECKING:
    from app.schemas.vehicle import VehicleResponse


class CustomerBase(BaseModel):
    first_name: str
    last_name: str
    company_name: Optional[str] = None
    email: str  # plain str to allow walk-in placeholder emails
    phone: Optional[str] = None
    billing_address_line1: Optional[str] = None
    billing_address_line2: Optional[str] = None
    billing_city: Optional[str] = None
    billing_state: Optional[str] = None
    billing_zip: Optional[str] = None
    billing_country: str = "USA"
    notes: Optional[str] = None
    auto_approval_threshold: Optional[Decimal] = None


class InitialVehicle(BaseModel):
    """Vehicle data for creating a customer with their first truck"""
    vin: Optional[str] = None
    unit_number: Optional[str] = None
    make: str
    model: str
    year: Optional[int] = None
    license_plate: Optional[str] = None
    color: Optional[str] = None
    mileage: Optional[int] = None
    notes: Optional[str] = None


class CustomerCreate(CustomerBase):
    initial_vehicle: Optional[InitialVehicle] = None
    no_vehicle: bool = False  # Explicit flag when customer has no truck


class CustomerUpdate(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    company_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    billing_address_line1: Optional[str] = None
    billing_address_line2: Optional[str] = None
    billing_city: Optional[str] = None
    billing_state: Optional[str] = None
    billing_zip: Optional[str] = None
    billing_country: Optional[str] = None
    notes: Optional[str] = None
    auto_approval_threshold: Optional[Decimal] = None


class CustomerResponse(CustomerBase):
    id: UUID
    tenant_id: UUID
    source: Optional[str] = None
    sms_opt_out: bool = False
    sms_opted_out_at: Optional[datetime] = None
    sms_opt_out_source: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class VehicleInCustomer(BaseModel):
    """Embedded vehicle schema for CustomerWithVehiclesResponse"""
    id: UUID
    tenant_id: UUID
    customer_id: UUID
    vin: Optional[str] = None
    unit_number: Optional[str] = None
    make: str
    model: str
    year: Optional[int] = None
    license_plate: Optional[str] = None
    color: Optional[str] = None
    mileage: Optional[int] = None
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class CustomerWithVehiclesResponse(CustomerBase):
    """Customer response that includes vehicles array"""
    id: UUID
    tenant_id: UUID
    source: Optional[str] = None
    sms_opt_out: bool = False
    sms_opted_out_at: Optional[datetime] = None
    sms_opt_out_source: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    vehicles: List[VehicleInCustomer] = Field(default_factory=list)
    
    class Config:
        from_attributes = True
