"""Immutable, tenant-scoped operator observations; no canonical vehicle writes."""

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import BaseModel


class FleetTelemetrySnapshot(BaseModel):
    __tablename__ = "fleet_telemetry_snapshots"
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    vehicle_id = Column(UUID(as_uuid=True), nullable=False)
    fleet_customer_id = Column(UUID(as_uuid=True), nullable=False)
    fleet_membership_id = Column(UUID(as_uuid=True), nullable=False)
    verified_vin = Column(String(17), nullable=False)
    client_request_id = Column(UUID(as_uuid=True), nullable=False)
    request_digest = Column(String(64), nullable=False)
    source = Column(String(40), nullable=False)
    observed_at = Column(DateTime(timezone=True))
    captured_at = Column(DateTime(timezone=True), nullable=False)
    captured_by_user_id = Column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    source_age_text = Column(String(120))
    provider_company_label = Column(String(255))
    provider_vehicle_id = Column(String(120))
    provider_vehicle_number = Column(String(120))
    location_label = Column(String(500))
    lat = Column(Float)
    lng = Column(Float)
    speed_mph = Column(Float)
    odometer_miles = Column(Float)
    engine_hours = Column(Float)
    fuel_percent = Column(Float)
    fault_count = Column(Integer)
    evidence_note = Column(String(1000))
    __table_args__ = (
        UniqueConstraint("tenant_id", "client_request_id", name="uq_telemetry_request"),
        ForeignKeyConstraint(
            ["tenant_id", "vehicle_id"], ["vehicles.tenant_id", "vehicles.id"]
        ),
        ForeignKeyConstraint(
            ["tenant_id", "fleet_customer_id"], ["customers.tenant_id", "customers.id"]
        ),
        ForeignKeyConstraint(
            ["tenant_id", "vehicle_id", "fleet_customer_id", "fleet_membership_id"],
            [
                "fleet_memberships.tenant_id",
                "fleet_memberships.vehicle_id",
                "fleet_memberships.fleet_customer_id",
                "fleet_memberships.id",
            ],
        ),
        Index("ix_telemetry_vehicle_capture", "tenant_id", "vehicle_id", "captured_at"),
        Index("ix_telemetry_retention", "captured_at"),
    )
