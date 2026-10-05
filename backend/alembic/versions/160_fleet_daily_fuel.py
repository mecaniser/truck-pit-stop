"""Independent immutable source-date fuel observations."""
from alembic import op
from sqlalchemy import Column, Date, DateTime, Numeric, ForeignKey, ForeignKeyConstraint, Integer, String, UniqueConstraint, CheckConstraint, func
from sqlalchemy.dialects.postgresql import UUID

revision = "160_fleet_daily_fuel"
down_revision = "159_fleet_trip_precision"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("fleet_daily_fuel_snapshots",
        Column("id", UUID(as_uuid=True), primary_key=True),
        Column("created_at", DateTime(timezone=True), server_default=func.now(), nullable=False),
        Column("updated_at", DateTime(timezone=True), server_default=func.now(), nullable=False),
        Column("deleted_at", DateTime(timezone=True)),
        Column("tenant_id", UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False),
        Column("vehicle_id", UUID(as_uuid=True), nullable=False),
        Column("fleet_customer_id", UUID(as_uuid=True), nullable=False),
        Column("fleet_membership_id", UUID(as_uuid=True), nullable=False),
        Column("verified_vin", String(17), nullable=False),
        Column("provider_company_id", String(120), nullable=False),
        Column("provider_vehicle_id", String(120), nullable=False),
        Column("provider_unit", String(120), nullable=False),
        Column("report_date", Date, nullable=False),
        Column("source", String(40), nullable=False),
        Column("source_timezone", String(100)),
        Column("timezone_status", String(20), nullable=False),
        Column("coverage_start", DateTime(timezone=True), nullable=False),
        Column("coverage_end", DateTime(timezone=True), nullable=False),
        Column("driving_fuel_gallons", Numeric(12, 3)),
        Column("idling_fuel_gallons", Numeric(12, 3)),
        Column("reported_total_fuel_gallons", Numeric(12, 3)),
        Column("source_distance_miles", Numeric(12, 3)),
        Column("source_driving_seconds", Integer),
        Column("source_idling_seconds", Integer),
        Column("source_read_at", DateTime(timezone=True), nullable=False),
        Column("source_receipt_sha256", String(64), nullable=False),
        Column("identity_receipt_sha256", String(64), nullable=False),
        Column("request_digest", String(64), nullable=False),
        Column("captured_at", DateTime(timezone=True), nullable=False),
        Column("captured_by_user_id", UUID(as_uuid=True), ForeignKey("users.id"), nullable=False),
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
    )
    op.create_index("ix_fleet_daily_fuel_snapshots_id", "fleet_daily_fuel_snapshots", ["id"])
    op.create_index("ix_fleet_fuel_date", "fleet_daily_fuel_snapshots", ["tenant_id", "report_date", "vehicle_id"])


def downgrade():
    # Application rollback can leave this additive table intact. Never erase evidence.
    op.execute("DO $$ BEGIN IF EXISTS (SELECT 1 FROM fleet_daily_fuel_snapshots) THEN RAISE EXCEPTION 'Retain revision 160: source fuel records exist'; END IF; END $$")
    op.drop_table("fleet_daily_fuel_snapshots")
