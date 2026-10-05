"""Immutable daily Motive fuel report observations, independent of trips."""
from sqlalchemy import Column, Date, DateTime, Numeric, ForeignKey, ForeignKeyConstraint, Index, Integer, String, UniqueConstraint, CheckConstraint
from sqlalchemy.dialects.postgresql import UUID
from app.db.base import BaseModel


class FleetFuelDaily(BaseModel):
    __tablename__ = "fleet_daily_fuel_snapshots"
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    vehicle_id = Column(UUID(as_uuid=True), nullable=False)
    fleet_customer_id = Column(UUID(as_uuid=True), nullable=False)
    fleet_membership_id = Column(UUID(as_uuid=True), nullable=False)
    verified_vin = Column(String(17), nullable=False)
    provider_company_id = Column(String(120), nullable=False)
    provider_vehicle_id = Column(String(120), nullable=False)
    provider_unit = Column(String(120), nullable=False)
    report_date = Column(Date, nullable=False)
    source = Column(String(40), nullable=False)
    source_timezone = Column(String(100))
    timezone_status = Column(String(20), nullable=False)
    coverage_start = Column(DateTime(timezone=True), nullable=False)
    coverage_end = Column(DateTime(timezone=True), nullable=False)
    driving_fuel_gallons = Column(Numeric(12, 3))
    idling_fuel_gallons = Column(Numeric(12, 3))
    reported_total_fuel_gallons = Column(Numeric(12, 3))
    source_distance_miles = Column(Numeric(12, 3))
    source_driving_seconds = Column(Integer)
    source_idling_seconds = Column(Integer)
    source_read_at = Column(DateTime(timezone=True), nullable=False)
    source_receipt_sha256 = Column(String(64), nullable=False)
    identity_receipt_sha256 = Column(String(64), nullable=False)
    request_digest = Column(String(64), nullable=False)
    captured_at = Column(DateTime(timezone=True), nullable=False)
    captured_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    __table_args__ = (
        UniqueConstraint("tenant_id", "provider_company_id", "provider_vehicle_id", "report_date", "source", name="uq_fleet_fuel_source_date"),
        ForeignKeyConstraint(["tenant_id", "vehicle_id"], ["vehicles.tenant_id", "vehicles.id"]),
        ForeignKeyConstraint(["tenant_id", "fleet_customer_id"], ["customers.tenant_id", "customers.id"]),
        ForeignKeyConstraint(["tenant_id", "vehicle_id", "fleet_customer_id", "fleet_membership_id"], ["fleet_memberships.tenant_id", "fleet_memberships.vehicle_id", "fleet_memberships.fleet_customer_id", "fleet_memberships.id"]),
        CheckConstraint("source = 'motive_vehicle_fuel_performance'", name="ck_fleet_fuel_source"),
        CheckConstraint("(timezone_status = 'unverified' AND source_timezone IS NULL) OR (timezone_status = 'verified' AND source_timezone IS NOT NULL)", name="ck_fleet_fuel_timezone"),
        CheckConstraint("coverage_end > coverage_start", name="ck_fleet_fuel_window"),
        CheckConstraint("driving_fuel_gallons IS NOT NULL OR idling_fuel_gallons IS NOT NULL OR reported_total_fuel_gallons IS NOT NULL", name="ck_fleet_fuel_reading"),
        CheckConstraint("driving_fuel_gallons >= 0 AND driving_fuel_gallons <= 10000 AND idling_fuel_gallons >= 0 AND idling_fuel_gallons <= 10000 AND reported_total_fuel_gallons >= 0 AND reported_total_fuel_gallons <= 20000", name="ck_fleet_fuel_gallons"),
        CheckConstraint("source_distance_miles >= 0 AND source_distance_miles <= 100000", name="ck_fleet_fuel_distance"),
        CheckConstraint("source_driving_seconds >= 0 AND source_driving_seconds <= 2678400 AND source_idling_seconds >= 0 AND source_idling_seconds <= 2678400", name="ck_fleet_fuel_seconds"),
        CheckConstraint("abs(reported_total_fuel_gallons - driving_fuel_gallons - idling_fuel_gallons) <= 0.15", name="ck_fleet_fuel_rounding"),
        Index("ix_fleet_fuel_date", "tenant_id", "report_date", "vehicle_id"),
    )
