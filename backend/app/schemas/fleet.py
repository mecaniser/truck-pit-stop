from datetime import datetime, date
from typing import Optional, List
from uuid import UUID

from pydantic import BaseModel

from app.db.models.fleet import (
    InspectionStatus,
    InspectionResult,
    InspectionItemResult,
    IncidentSeverity,
    IncidentStatus,
)


# ---- Inspections ----

class InspectionItemResponse(BaseModel):
    id: UUID
    category: str
    label: str
    is_warning_light: bool = False
    result: InspectionItemResult
    note: Optional[str] = None

    class Config:
        from_attributes = True


class InspectionItemUpdate(BaseModel):
    result: Optional[InspectionItemResult] = None
    note: Optional[str] = None


class InspectionCreate(BaseModel):
    vehicle_id: UUID
    scheduled_for: Optional[date] = None  # defaults to today


class InspectionComplete(BaseModel):
    odometer: Optional[int] = None
    notes: Optional[str] = None
    result: Optional[InspectionResult] = None  # override; otherwise computed from items


class WorkOrderComplete(BaseModel):
    # Odometer at completion. Optional: when omitted, mileage_out is taken from
    # the truck's current odometer. Provided as a manual fallback when the
    # vehicle odometer isn't current.
    mileage_out: Optional[int] = None
    # Optional manager notes captured during the quality-review approval.
    review_notes: Optional[str] = None


class InspectionResponse(BaseModel):
    id: UUID
    vehicle_id: UUID
    inspector_id: Optional[UUID] = None
    status: InspectionStatus
    result: Optional[InspectionResult] = None
    scheduled_for: date
    performed_at: Optional[datetime] = None
    odometer: Optional[int] = None
    notes: Optional[str] = None
    repair_order_id: Optional[UUID] = None  # work order created to fix failed items
    created_at: datetime
    # Denormalized vehicle summary
    vehicle_make: str = ""
    vehicle_model: str = ""
    vehicle_year: Optional[int] = None
    vehicle_unit_number: Optional[str] = None

    class Config:
        from_attributes = True


class InspectionDetailResponse(InspectionResponse):
    items: List[InspectionItemResponse] = []


# ---- Incidents ----

class FleetPhotoResponse(BaseModel):
    id: UUID
    image_url: str
    caption: Optional[str] = None
    uploaded_at: datetime
    uploader_name: str = "Unknown"


class IncidentCreate(BaseModel):
    vehicle_id: UUID
    occurred_at: datetime
    location: Optional[str] = None
    severity: IncidentSeverity = IncidentSeverity.MEDIUM
    description: str


class IncidentUpdate(BaseModel):
    status: Optional[IncidentStatus] = None
    severity: Optional[IncidentSeverity] = None
    location: Optional[str] = None
    description: Optional[str] = None
    resolution_notes: Optional[str] = None


class IncidentResponse(BaseModel):
    id: UUID
    vehicle_id: UUID
    reported_by_id: Optional[UUID] = None
    occurred_at: datetime
    location: Optional[str] = None
    severity: IncidentSeverity
    status: IncidentStatus
    description: str
    resolution_notes: Optional[str] = None
    resolved_at: Optional[datetime] = None
    repair_order_id: Optional[UUID] = None
    created_at: datetime
    photos: List[FleetPhotoResponse] = []
    # Denormalized vehicle summary
    vehicle_make: str = ""
    vehicle_model: str = ""
    vehicle_year: Optional[int] = None
    vehicle_unit_number: Optional[str] = None

    class Config:
        from_attributes = True


# ---- Roster & summary ----

class FleetVehicleResponse(BaseModel):
    id: UUID
    make: str
    model: str
    year: Optional[int] = None
    unit_number: Optional[str] = None
    vin: Optional[str] = None
    license_plate: Optional[str] = None
    mileage: Optional[int] = None
    last_inspection_at: Optional[datetime] = None
    last_inspection_result: Optional[InspectionResult] = None
    next_inspection_due: Optional[date] = None
    inspection_overdue: bool = False
    open_incident_count: int = 0


class FleetSummaryResponse(BaseModel):
    total_vehicles: int
    inspections_due: int       # scheduled inspections not yet overdue
    inspections_overdue: int
    open_incidents: int


# ---- Fleet board (design: truck card grid + KPI strip) ----

FleetTruckStatus = str  # 'active' | 'shop' | 'pm' | 'parts'


class PMServiceEntry(BaseModel):
    """A service attached to a truck's PM package or a PM work order."""
    service_id: UUID
    name: str
    duration_minutes: int = 0
    sort_order: int = 0

    class Config:
        from_attributes = True


class BoardWorkOrder(BaseModel):
    id: str                 # order_number
    repair_order_id: UUID   # actual RO id, for opening/editing the work order
    status: str             # shop-floor label (In progress, Awaiting parts, …)
    raw_status: str = ""    # underlying RO status value (draft, in_progress, …) for lifecycle gating
    summary: Optional[str] = None
    mechanic: Optional[str] = None
    is_pm: bool = False      # this work order is the truck's preventive-maintenance job


class BoardTruck(BaseModel):
    id: UUID
    unit_number: Optional[str] = None
    year: Optional[int] = None
    make: str
    model: str
    brand_short: Optional[str] = None
    body_type: Optional[str] = None
    vin: Optional[str] = None
    plate: Optional[str] = None
    status: FleetTruckStatus
    driver_name: Optional[str] = None
    driver_phone: Optional[str] = None
    odometer: Optional[int] = None
    pm_interval_miles: int = 25000
    next_pm_miles: Optional[int] = None
    pm_remaining: Optional[int] = None
    pm_interval_days: int = 70
    pm_due_date: Optional[date] = None
    pm_days_remaining: Optional[int] = None
    location_label: Optional[str] = None
    location_city: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    moving: bool = False
    speed_mph: Optional[int] = None
    heading: Optional[str] = None
    assigned_mechanic: Optional[str] = None
    work_order: Optional[BoardWorkOrder] = None  # most-urgent open work order
    pm_work_order: Optional[BoardWorkOrder] = None  # the truck's open PM work order, if one exists
    pm_services: List[PMServiceEntry] = []  # the truck's saved default PM service package
    open_work_order_count: int = 0
    open_incident_count: int = 0
    status_override: Optional[str] = None  # operator's manual idle status, if set
    warning_lights: List[str] = []  # dashboard warning lights currently on
    fleet_customer_id: Optional[UUID] = None
    fleet_company_name: Optional[str] = None
    owner_customer_id: Optional[UUID] = None
    owner_company_name: Optional[str] = None


class FleetStats(BaseModel):
    total: int
    active: int
    shop: int
    pm: int
    parts: int
    open_wo: int
    incidents_total: int


class FleetBoardResponse(BaseModel):
    trucks: List[BoardTruck]
    stats: FleetStats


# ---- Truck detail ----

class HistoryEntry(BaseModel):
    id: UUID
    date: Optional[datetime] = None
    kind: str               # 'PM' | 'Repair' | 'Inspection'
    odometer: Optional[int] = None
    summary: Optional[str] = None
    mechanic: Optional[str] = None
    cost: Optional[float] = None


class PartEntry(BaseModel):
    id: UUID
    name: str
    date: Optional[datetime] = None
    odometer: Optional[int] = None
    mechanic: Optional[str] = None
    warranty_until: Optional[date] = None
    warranty_miles: Optional[int] = None
    active: bool = False


class IncidentEntry(BaseModel):
    id: UUID
    date: datetime
    type: str
    severity: IncidentSeverity
    status: IncidentStatus
    location: Optional[str] = None
    note: Optional[str] = None
    repair_order_id: Optional[UUID] = None
    photos: List[FleetPhotoResponse] = []


class NearestUnit(BaseModel):
    id: UUID
    unit_number: Optional[str] = None
    city: Optional[str] = None
    status: FleetTruckStatus
    miles: int


class TruckDetailResponse(BaseModel):
    truck: BoardTruck
    open_work_orders: List[BoardWorkOrder] = []
    driver_phone: Optional[str] = None
    billing_contact_name: Optional[str] = None
    billing_contact_email: Optional[str] = None
    billing_contact_phone: Optional[str] = None
    bill_labor_at_customer_rate: bool = False
    lifetime_spend: float = 0.0
    incidents_count: int = 0
    crew: List[str] = []
    history: List[HistoryEntry] = []
    parts: List[PartEntry] = []
    incidents: List[IncidentEntry] = []
    nearest: List[NearestUnit] = []


class TruckUpdate(BaseModel):
    # Identity (correctable after creation — VIN decode is sometimes wrong/generic).
    unit_number: Optional[str] = None
    vin: Optional[str] = None
    make: Optional[str] = None
    model: Optional[str] = None
    year: Optional[int] = None
    license_plate: Optional[str] = None
    # Operational
    driver_name: Optional[str] = None
    driver_phone: Optional[str] = None
    billing_contact_name: Optional[str] = None
    billing_contact_email: Optional[str] = None
    billing_contact_phone: Optional[str] = None
    bill_labor_at_customer_rate: Optional[bool] = None
    odometer: Optional[int] = None
    pm_interval_miles: Optional[int] = None
    next_pm_miles: Optional[int] = None
    pm_interval_days: Optional[int] = None
    pm_due_date: Optional[date] = None
    telematics_device_id: Optional[str] = None
    # Manual location entry (used until a telematics provider is connected).
    lat: Optional[float] = None
    lng: Optional[float] = None
    location_label: Optional[str] = None
    location_city: Optional[str] = None
    speed_mph: Optional[int] = None
    heading: Optional[str] = None
    # Manual idle status: 'active' | 'yard' | 'available' | 'out_of_service' |
    # 'auto' ('auto' or '' clears the override).
    status_override: Optional[str] = None


class WorkOrderCreate(BaseModel):
    # Optional description of the work needed; defaults server-side when blank.
    description: Optional[str] = None
    # Visit-specific payer. Defaults to the truck's primary/default account.
    bill_to_customer_id: Optional[UUID] = None


class PMServicesUpdate(BaseModel):
    """Replace the full set of PM services (order preserved) for a truck default
    package or a PM work order."""
    service_ids: List[UUID] = []


class AddServiceRequest(BaseModel):
    """Add a single catalog service (e.g. Diagnostic) to a non-PM internal work
    order, seeding an internal-rate labor line plus the service's parts."""
    service_id: UUID


class SchedulePMRequest(BaseModel):
    due_date: Optional[date] = None            # scheduled/next PM date
    next_pm_miles: Optional[int] = None         # odometer at which the next PM is due
    create_work_order: bool = False             # also spawn the PM work order now
    # Services for this PM. When None, the truck's saved default package is used.
    # When provided, these override the default for this PM (order preserved).
    service_ids: Optional[List[UUID]] = None
    # Also save service_ids as the truck's new default PM package.
    save_as_default: bool = False
    bill_to_customer_id: Optional[UUID] = None


class FleetCompanyOption(BaseModel):
    id: UUID
    company_name: str
    fleet_enabled: bool = False
    is_internal_fleet: bool = False


class FleetMembershipCreate(BaseModel):
    vehicle_id: UUID
    fleet_customer_id: UUID


class FleetTruckCreate(BaseModel):
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
    driver_name: Optional[str] = None
    driver_phone: Optional[str] = None


class FleetMechanicOption(BaseModel):
    id: UUID
    name: str


class FleetManagerOption(BaseModel):
    id: UUID
    name: str
    email: str


class FleetInvoiceEntry(BaseModel):
    id: UUID
    invoice_number: str
    repair_order_id: UUID
    order_number: Optional[str] = None
    status: str
    total_amount: float
    created_at: datetime
    # Truck context
    vehicle_id: Optional[UUID] = None
    unit_number: Optional[str] = None
    vehicle_label: Optional[str] = None


class FleetSettingsResponse(BaseModel):
    # In-house labor cost rate, configured by owner/admin in garage settings.
    internal_labor_rate: float = 0.0
    labor_rate: float = 0.0
    # Name of the company that operates the internal fleet (e.g. "77 Cargo").
    fleet_company_name: Optional[str] = None
    # Users who manage the fleet (FLEET_MANAGER role in this tenant).
    fleet_managers: List[FleetManagerOption] = []
    # Live count of trucks on the fleet board (vehicles on the house account).
    truck_count: int = 0
