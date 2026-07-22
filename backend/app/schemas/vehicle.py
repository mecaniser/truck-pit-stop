from pydantic import BaseModel, Field
from typing import List, Literal, Optional
from datetime import datetime
from uuid import UUID


class VehicleBase(BaseModel):
    vin: Optional[str] = None
    unit_number: Optional[str] = None
    make: str
    model: str
    year: Optional[int] = None
    license_plate: Optional[str] = None
    color: Optional[str] = None
    mileage: Optional[int] = None
    notes: Optional[str] = None


class VehicleCreate(VehicleBase):
    customer_id: UUID
    # Optional driver assignment at creation (driver is two simple fields on the
    # vehicle, not a managed entity).
    driver_name: Optional[str] = None
    driver_phone: Optional[str] = None


class VehicleUpdate(BaseModel):
    vin: Optional[str] = None
    unit_number: Optional[str] = None
    make: Optional[str] = None
    model: Optional[str] = None
    year: Optional[int] = None
    license_plate: Optional[str] = None
    color: Optional[str] = None
    mileage: Optional[int] = None
    notes: Optional[str] = None


class VehicleCustomerUpdate(BaseModel):
    """Limited update schema for customers - only license plate"""
    license_plate: Optional[str] = None


class VehicleResponse(VehicleBase):
    id: UUID
    tenant_id: UUID
    customer_id: UUID
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


VehicleRelationshipType = Literal["owner", "operator", "default_payer"]


class VehicleRelationshipCreate(BaseModel):
    customer_id: UUID
    relationship_type: VehicleRelationshipType
    is_primary: bool = False
    # Ownership/default-payer changes close the previous primary period instead
    # of rewriting it, preserving the truck's business history.
    replace_primary: bool = False


class VehicleRelationshipSync(BaseModel):
    """Replace one customer's active roles for a truck in one operation."""

    customer_id: UUID
    relationship_types: List[VehicleRelationshipType] = Field(default_factory=list)
    # The operating authority is independent from the customer whose profile
    # is currently being edited. This lets an owner/lessor assign, for example,
    # 77 Cargo as authority without making 77 Cargo the owner or payer.
    operating_authority_customer_id: Optional[UUID] = None
    # Canonical unit only; company prefixes are derived for fleet displays.
    unit_number: Optional[str] = None


class VehicleRelationshipResponse(BaseModel):
    id: UUID
    vehicle_id: UUID
    customer_id: UUID
    relationship_type: VehicleRelationshipType
    effective_from: datetime
    effective_to: Optional[datetime] = None
    is_primary: bool = False
    customer_company_name: Optional[str] = None

    class Config:
        from_attributes = True
