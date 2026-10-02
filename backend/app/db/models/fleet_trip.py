"""Immutable completed journeys observed in the Motive dashboard."""
from sqlalchemy import Column, DateTime, Float, ForeignKey, ForeignKeyConstraint, Index, Integer, String, UniqueConstraint, CheckConstraint, JSON
from sqlalchemy.dialects.postgresql import UUID
from app.db.base import BaseModel


class FleetTrip(BaseModel):
    __tablename__ = "fleet_trip_snapshots"
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    vehicle_id = Column(UUID(as_uuid=True), nullable=False)
    fleet_customer_id = Column(UUID(as_uuid=True), nullable=False)
    fleet_membership_id = Column(UUID(as_uuid=True), nullable=False)
    verified_vin = Column(String(17), nullable=False)
    provider_vehicle_id = Column(String(120), nullable=False)
    provider_unit = Column(String(120), nullable=False)
    source_read_at = Column(DateTime(timezone=True), nullable=False)
    request_digest = Column(String(64), nullable=False)
    source = Column(String(40), nullable=False)
    started_at = Column(DateTime(timezone=True), nullable=False)
    ended_at = Column(DateTime(timezone=True), nullable=False)
    origin_label = Column(String(500), nullable=False)
    destination_label = Column(String(500), nullable=False)
    distance_miles = Column(Float, nullable=False)
    driving_seconds = Column(Integer, nullable=False)
    stops = Column(JSON, nullable=True)
    metrics = Column(JSON, nullable=True)
    captured_at = Column(DateTime(timezone=True), nullable=False)
    captured_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    __table_args__ = (
        UniqueConstraint("tenant_id", "provider_vehicle_id", "started_at", name="uq_fleet_trip_departure"),
        ForeignKeyConstraint(["tenant_id", "vehicle_id"], ["vehicles.tenant_id", "vehicles.id"]),
        ForeignKeyConstraint(["tenant_id", "fleet_customer_id"], ["customers.tenant_id", "customers.id"]),
        ForeignKeyConstraint(["tenant_id", "vehicle_id", "fleet_customer_id", "fleet_membership_id"], ["fleet_memberships.tenant_id", "fleet_memberships.vehicle_id", "fleet_memberships.fleet_customer_id", "fleet_memberships.id"]),
        CheckConstraint("ended_at > started_at", name="ck_fleet_trip_completed"),
        CheckConstraint("distance_miles >= 0 AND distance_miles <= 100000", name="ck_fleet_trip_distance"),
        CheckConstraint("driving_seconds >= 0 AND driving_seconds <= EXTRACT(EPOCH FROM (ended_at - started_at))", name="ck_fleet_trip_driving").ddl_if(dialect="postgresql"),
        CheckConstraint("driving_seconds >= 0 AND driving_seconds <= 2678400", name="ck_fleet_trip_driving_bound"),
        CheckConstraint("source = 'motive_dashboard_manual'", name="ck_fleet_trip_source"),
        Index("ix_fleet_trip_departure", "tenant_id", "started_at", "vehicle_id"),
    )
