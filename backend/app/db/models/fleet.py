"""Fleet management models: weekly inspections and roadside incidents.

These workflows are scoped to the garage's own internal fleet (see
``Customer.is_internal_fleet``) and surfaced through the Fleet section to the
fleet manager (and the garage owner/admin who own the fleet).
"""
from sqlalchemy import (
    Column,
    String,
    Text,
    Integer,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Enum as SQLEnum,
)
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID
import enum
from app.db.base import BaseModel


# Weekly cadence for fleet inspections.
INSPECTION_INTERVAL_DAYS = 7

# Default checklist template instantiated for each new inspection. Fixed in code
# for v1; (category, label) pairs become FleetInspectionItem rows.
# Checklist items are (category, label, is_warning_light). A warning-light item
# is a dashboard telltale grouped inline with the related physical checks;
# marking it FAIL means that light is illuminated and needs attention.
DEFAULT_INSPECTION_CHECKLIST: list[tuple[str, str, bool]] = [
    ("Brakes", "Brake pads & rotors", False),
    ("Brakes", "Air brake system / lines", False),
    ("Brakes", "ABS", True),
    ("Brakes", "Brake / low air", True),
    ("Tires", "Tread depth & wear", False),
    ("Tires", "Tire pressure", False),
    ("Tires", "Tire pressure (TPMS)", True),
    ("Lights", "Headlights & turn signals", False),
    ("Lights", "Brake & marker lights", False),
    ("Fluids", "Engine oil level", False),
    ("Fluids", "Coolant level", False),
    ("Fluids", "Leaks under vehicle", False),
    ("Fluids", "Oil pressure", True),
    ("Fluids", "Coolant temp", True),
    ("Engine & emissions", "Check engine (MIL)", True),
    ("Engine & emissions", "DEF low", True),
    ("Steering", "Steering & suspension play", False),
    ("Safety", "Horn, wipers & mirrors", False),
    ("Safety", "Seatbelts & fire extinguisher", False),
]


class InspectionStatus(str, enum.Enum):
    SCHEDULED = "scheduled"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    MISSED = "missed"  # weekly cadence lapsed with no inspection performed


class InspectionResult(str, enum.Enum):
    PASS = "pass"
    ATTENTION = "attention"  # passed overall but some items need attention
    FAIL = "fail"


class InspectionItemResult(str, enum.Enum):
    PENDING = "pending"
    PASS = "pass"
    FAIL = "fail"
    NA = "na"


class IncidentSeverity(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class IncidentStatus(str, enum.Enum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"


def _enum_col(enum_cls, **kwargs):
    return Column(
        SQLEnum(enum_cls, values_callable=lambda e: [m.value for m in e]),
        **kwargs,
    )


class FleetInspection(BaseModel):
    __tablename__ = "fleet_inspections"

    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    vehicle_id = Column(UUID(as_uuid=True), ForeignKey("vehicles.id"), nullable=False, index=True)
    inspector_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)

    status = _enum_col(InspectionStatus, nullable=False, default=InspectionStatus.SCHEDULED, index=True)
    result = _enum_col(InspectionResult, nullable=True)

    scheduled_for = Column(Date, nullable=False, index=True)
    performed_at = Column(DateTime(timezone=True), nullable=True)
    odometer = Column(Integer, nullable=True)
    notes = Column(Text, nullable=True)
    # Work order created to fix this inspection's failed items (traceability).
    repair_order_id = Column(UUID(as_uuid=True), ForeignKey("repair_orders.id"), nullable=True)

    vehicle = relationship("Vehicle")
    inspector = relationship("User", foreign_keys=[inspector_id])
    items = relationship(
        "FleetInspectionItem",
        back_populates="inspection",
        cascade="all, delete-orphan",
    )


class FleetInspectionItem(BaseModel):
    __tablename__ = "fleet_inspection_items"

    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    inspection_id = Column(
        UUID(as_uuid=True), ForeignKey("fleet_inspections.id"), nullable=False, index=True
    )
    category = Column(String(80), nullable=False)
    label = Column(String(160), nullable=False)
    # Dashboard warning/telltale light (vs a physical check). FAIL = illuminated.
    is_warning_light = Column(Boolean, nullable=False, default=False)
    result = _enum_col(InspectionItemResult, nullable=False, default=InspectionItemResult.PENDING)
    note = Column(Text, nullable=True)

    inspection = relationship("FleetInspection", back_populates="items")


class FleetIncident(BaseModel):
    __tablename__ = "fleet_incidents"

    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    vehicle_id = Column(UUID(as_uuid=True), ForeignKey("vehicles.id"), nullable=False, index=True)
    reported_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)

    occurred_at = Column(DateTime(timezone=True), nullable=False)
    location = Column(String(255), nullable=True)
    severity = _enum_col(IncidentSeverity, nullable=False, default=IncidentSeverity.MEDIUM, index=True)
    status = _enum_col(IncidentStatus, nullable=False, default=IncidentStatus.OPEN, index=True)
    description = Column(Text, nullable=False)
    resolution_notes = Column(Text, nullable=True)
    resolved_at = Column(DateTime(timezone=True), nullable=True)

    # Optional internal repair order spawned to fix the incident.
    repair_order_id = Column(
        UUID(as_uuid=True), ForeignKey("repair_orders.id"), nullable=True, index=True
    )

    vehicle = relationship("Vehicle")
    reported_by = relationship("User", foreign_keys=[reported_by_id])
    repair_order = relationship("RepairOrder")
    photos = relationship("FleetIncidentPhoto", back_populates="incident", cascade="all, delete-orphan")


class FleetIncidentPhoto(BaseModel):
    __tablename__ = "fleet_incident_photos"

    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    incident_id = Column(UUID(as_uuid=True), ForeignKey("fleet_incidents.id", ondelete="CASCADE"), nullable=False, index=True)
    uploaded_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True)
    image_url = Column(String(500), nullable=False)
    cloudinary_public_id = Column(String(255), nullable=True)
    caption = Column(String(500), nullable=True)
    uploaded_at = Column(DateTime(timezone=True), nullable=False)

    incident = relationship("FleetIncident", back_populates="photos")
    uploaded_by = relationship("User", foreign_keys=[uploaded_by_id])


class VehiclePMService(BaseModel):
    """A truck's saved default PM service package. Each row links a truck to a
    catalog Service that should be part of that truck's preventive maintenance.
    Scheduling a PM copies these onto the work order (see RepairOrderPMService),
    where they can then be adjusted per-PM without changing this default."""
    __tablename__ = "vehicle_pm_services"

    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    vehicle_id = Column(UUID(as_uuid=True), ForeignKey("vehicles.id"), nullable=False, index=True)
    service_id = Column(UUID(as_uuid=True), ForeignKey("services.id"), nullable=False, index=True)
    sort_order = Column(Integer, nullable=False, default=0)

    vehicle = relationship("Vehicle")
    service = relationship("Service")


class RepairOrderPMService(BaseModel):
    """The services attached to a specific PM work order. Copied from the truck's
    default package (VehiclePMService) at creation, then editable per-PM. Drives
    the manager-facing PM scope (work order description) and the owner-facing
    seeded labor/parts cost lines."""
    __tablename__ = "repair_order_pm_services"

    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    repair_order_id = Column(UUID(as_uuid=True), ForeignKey("repair_orders.id"), nullable=False, index=True)
    service_id = Column(UUID(as_uuid=True), ForeignKey("services.id"), nullable=False, index=True)
    sort_order = Column(Integer, nullable=False, default=0)

    repair_order = relationship("RepairOrder")
    service = relationship("Service")
