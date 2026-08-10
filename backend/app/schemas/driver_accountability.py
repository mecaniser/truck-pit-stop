from datetime import date, datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class DriverProfileCreate(BaseModel):
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    employer_customer_id: Optional[UUID] = None
    phone: Optional[str] = Field(default=None, max_length=20)
    email: Optional[str] = Field(default=None, max_length=255)
    employee_number: Optional[str] = Field(default=None, max_length=80)


class DriverProfileUpdate(BaseModel):
    first_name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    last_name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    employer_customer_id: Optional[UUID] = None
    phone: Optional[str] = Field(default=None, max_length=20)
    email: Optional[str] = Field(default=None, max_length=255)
    employee_number: Optional[str] = Field(default=None, max_length=80)
    employment_status: Optional[str] = Field(default=None, pattern="^(active|inactive)$")


class DriverProfileResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    user_id: Optional[UUID] = None
    employer_customer_id: Optional[UUID] = None
    first_name: str
    last_name: str
    phone: Optional[str] = None
    email: Optional[str] = None
    employee_number: Optional[str] = None
    license_number: Optional[str] = None
    license_state: Optional[str] = None
    license_expires_on: Optional[date] = None
    employment_status: str

    class Config:
        from_attributes = True


class LegacyDriverContactResponse(BaseModel):
    name: str
    phone: Optional[str] = None
    vehicle_count: int = Field(ge=1)


class TrailerCreate(BaseModel):
    owner_customer_id: Optional[UUID] = None
    vin: Optional[str] = Field(default=None, min_length=17, max_length=17)
    unit_number: Optional[str] = Field(default=None, max_length=50)
    make: Optional[str] = Field(default=None, max_length=100)
    model: Optional[str] = Field(default=None, max_length=100)
    year: Optional[int] = Field(default=None, ge=1900, le=2200)
    license_plate: Optional[str] = Field(default=None, max_length=20)
    body_type: Optional[str] = Field(default=None, max_length=80)
    notes: Optional[str] = None


class TrailerResponse(TrailerCreate):
    id: UUID
    tenant_id: UUID
    status: str

    class Config:
        from_attributes = True


class CustodyAssignmentCreate(BaseModel):
    driver_id: UUID
    vehicle_id: UUID
    trailer_ids: list[UUID] = Field(default_factory=list)
    starts_at: Optional[datetime] = None
    start_odometer: Optional[int] = Field(default=None, ge=0)
    dispatch_reference: Optional[str] = Field(default=None, max_length=120)
    handoff_notes: Optional[str] = None


class CustodyAssetResponse(BaseModel):
    id: UUID
    vehicle_id: Optional[UUID] = None
    trailer_id: Optional[UUID] = None
    equipment_role: str
    attached_at: datetime
    released_at: Optional[datetime] = None
    start_odometer: Optional[int] = None
    end_odometer: Optional[int] = None

    class Config:
        from_attributes = True


class CustodySessionResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    driver_id: UUID
    status: str
    starts_at: datetime
    acknowledged_at: Optional[datetime] = None
    ends_at: Optional[datetime] = None
    dispatch_reference: Optional[str] = None
    handoff_notes: Optional[str] = None
    assets: list[CustodyAssetResponse] = Field(default_factory=list)

    class Config:
        from_attributes = True


class VehicleDriverAssignmentResponse(BaseModel):
    vehicle_id: UUID
    custody_session_id: UUID
    custody_status: str
    custody_starts_at: datetime
    custody_acknowledged_at: Optional[datetime] = None
    driver: DriverProfileResponse


class AssignedEquipmentResponse(BaseModel):
    custody_session_id: UUID
    custody_status: str
    custody_starts_at: datetime
    custody_acknowledged_at: Optional[datetime] = None
    asset_id: UUID
    equipment_role: str
    vehicle_id: Optional[UUID] = None
    trailer_id: Optional[UUID] = None
    unit_number: Optional[str] = None
    vin: Optional[str] = None
    make: Optional[str] = None
    model: Optional[str] = None
    year: Optional[int] = None
    license_plate: Optional[str] = None
    odometer: Optional[int] = None


class DriverInspectionCreate(BaseModel):
    vehicle_id: UUID


class DriverIncidentCreate(BaseModel):
    vehicle_id: UUID
    trailer_id: Optional[UUID] = None
    occurred_at: datetime
    incident_type: str = Field(default="other", min_length=1, max_length=32)
    location: Optional[str] = Field(default=None, max_length=255)
    severity: str = Field(default="medium", pattern="^(low|medium|high|critical)$")
    description: str = Field(min_length=1, max_length=5000)


class DriverScorecardResponse(BaseModel):
    driver_id: UUID
    custody_sessions: int
    custody_miles: int
    incidents_during_custody: int
    open_incidents: int
    finalized_reviews: int
    confirmed_driver_duty_issues: int
    shared_responsibility_findings: int
    not_attributable_findings: int
    insufficient_evidence_findings: int
    disputed_or_pending_reviews: int
    reviewed_duty_issue_rate_per_10k_miles: Optional[float] = None
    scoring_ready: bool = False
