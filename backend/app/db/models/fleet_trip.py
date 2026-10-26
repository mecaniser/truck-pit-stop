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
    verified_vin = Column(String(17), nullable=True)
    dashboard_binding_id = Column(UUID(as_uuid=True), nullable=True)
    source_company_id = Column(String(120), nullable=True)
    source_company_label = Column(String(255), nullable=True)
    source_vin_state = Column(String(30), nullable=True)
    provider_vehicle_id = Column(String(120), nullable=False)
    provider_unit = Column(String(120), nullable=False)
    timestamp_precision = Column(String(10), nullable=False, default="second", server_default="second")
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
        ForeignKeyConstraint(["tenant_id", "vehicle_id", "fleet_membership_id", "dashboard_binding_id"], ["dashboard_vehicle_bindings.tenant_id", "dashboard_vehicle_bindings.vehicle_id", "dashboard_vehicle_bindings.fleet_membership_id", "dashboard_vehicle_bindings.id"], name="fk_trip_dashboard_binding"),
        CheckConstraint("(verified_vin IS NOT NULL AND dashboard_binding_id IS NULL AND source_company_id IS NULL AND source_company_label IS NULL AND source_vin_state IS NULL) OR (verified_vin IS NULL AND dashboard_binding_id IS NOT NULL AND source_company_id = 'KT8934277' AND source_company_id IS NOT NULL AND source_company_label = '77 CARGO LLC' AND source_company_label IS NOT NULL AND provider_vehicle_id = '5981300' AND source_vin_state IN ('not_displayed', 'explicitly_empty') AND source_vin_state IS NOT NULL)", name="ck_trip_identity_xor"),
        UniqueConstraint("tenant_id", "id", name="uq_fleet_trip_tenant_id"),
        UniqueConstraint("tenant_id", "provider_vehicle_id", "started_at", name="uq_fleet_trip_departure"),
        ForeignKeyConstraint(["tenant_id", "vehicle_id"], ["vehicles.tenant_id", "vehicles.id"]),
        ForeignKeyConstraint(["tenant_id", "fleet_customer_id"], ["customers.tenant_id", "customers.id"]),
        ForeignKeyConstraint(["tenant_id", "vehicle_id", "fleet_customer_id", "fleet_membership_id"], ["fleet_memberships.tenant_id", "fleet_memberships.vehicle_id", "fleet_memberships.fleet_customer_id", "fleet_memberships.id"]),
        CheckConstraint("ended_at > started_at OR (timestamp_precision = 'minute' AND ended_at = started_at AND driving_seconds > 0)", name="ck_fleet_trip_completed"),
        CheckConstraint("timestamp_precision IN ('second', 'minute')", name="ck_fleet_trip_precision"),
        CheckConstraint("timestamp_precision <> 'minute' OR (date_trunc('minute', started_at) = started_at AND date_trunc('minute', ended_at) = ended_at)", name="ck_fleet_trip_minute_aligned").ddl_if(dialect="postgresql"),
        CheckConstraint("distance_miles >= 0 AND distance_miles <= 100000", name="ck_fleet_trip_distance"),
        CheckConstraint("driving_seconds >= 0 AND driving_seconds <= EXTRACT(EPOCH FROM (ended_at - started_at)) + CASE WHEN timestamp_precision = 'minute' THEN 59 ELSE 0 END", name="ck_fleet_trip_driving").ddl_if(dialect="postgresql"),
        CheckConstraint("driving_seconds >= 0 AND driving_seconds <= 2678400", name="ck_fleet_trip_driving_bound"),
        CheckConstraint("source = 'motive_dashboard_manual'", name="ck_fleet_trip_source"),
        Index("ix_fleet_trip_departure", "tenant_id", "started_at", "vehicle_id"),
    )


class FleetTripRevision(BaseModel):
    """Append-only operator correction audit; no application update/delete path."""
    __tablename__ = "fleet_trip_revisions"
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    trip_id = Column(UUID(as_uuid=True), nullable=False)
    old_digest = Column(String(64), nullable=False)
    replacement_digest = Column(String(64), nullable=False)
    old_snapshot = Column(JSON, nullable=False)
    reason = Column(String(500), nullable=False)
    corrected_at = Column(DateTime(timezone=True), nullable=False)
    corrected_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    __table_args__ = (
        ForeignKeyConstraint(["tenant_id", "trip_id"], ["fleet_trip_snapshots.tenant_id", "fleet_trip_snapshots.id"]),
        UniqueConstraint("tenant_id", "trip_id", "old_digest", name="uq_fleet_trip_revision_predecessor"),
    )
