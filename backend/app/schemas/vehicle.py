from pydantic import BaseModel, Field
from typing import Dict, List, Literal, Optional
from datetime import datetime
from decimal import Decimal
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
    # Net accounts receivable for this truck in the customer context used by
    # the listing endpoint. Positive means due; negative means customer credit.
    balance: Decimal = Decimal("0.00")
    # Active roles for the customer whose profile requested this vehicle.
    # Billing-only relationships are intentionally not returned as vehicles.
    customer_relationship_types: List[Literal["owner", "operator"]] = Field(default_factory=list)
    owner_customer_id: Optional[UUID] = None
    owner_company_name: Optional[str] = None
    operating_authority_customer_id: Optional[UUID] = None
    operating_authority_company_name: Optional[str] = None
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


class VehicleMergeRequest(BaseModel):
    duplicate_vehicle_id: UUID
    # The UI repeats the matched identity so a stale or accidental selection
    # cannot merge a different physical truck. Exactly one is expected based on
    # the server-generated preview.
    confirm_vin: Optional[str] = Field(default=None, min_length=17, max_length=17)
    confirm_unit_number: Optional[str] = Field(default=None, min_length=1, max_length=50)


class VehicleMergeVehicleSummary(BaseModel):
    id: UUID
    customer_id: UUID
    customer_name: str
    vin: str
    unit_number: Optional[str] = None
    make: str
    model: str
    year: Optional[int] = None
    license_plate: Optional[str] = None
    mileage: Optional[int] = None
    source: Optional[str] = None
    ets_external_id: Optional[str] = None
    repair_order_count: int = 0
    appointment_count: int = 0
    inspection_count: int = 0
    incident_count: int = 0
    active_relationship_count: int = 0
    active_fleet_membership_count: int = 0
    repair_orders_by_source: Dict[str, int] = Field(default_factory=dict)


class VehicleMergePreview(BaseModel):
    canonical: VehicleMergeVehicleSummary
    duplicate: VehicleMergeVehicleSummary
    match_basis: str
    match_value: str
    recommended_canonical_id: UUID
    warnings: List[str] = Field(default_factory=list)


class VehicleMergeResult(BaseModel):
    canonical_vehicle: VehicleResponse
    archived_vehicle_id: UUID
    merge_record_id: UUID
    moved: Dict[str, int]
