"""Immutable imported completed trips."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
revision = "158_fleet_trips"
down_revision = "157_fleet_fuel_economy"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "fleet_trip_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("vehicle_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("fleet_customer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("fleet_membership_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("verified_vin", sa.String(17), nullable=False),
        sa.Column("provider_vehicle_id", sa.String(120), nullable=False),
        sa.Column("provider_unit", sa.String(120), nullable=False),
        sa.Column("source_read_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("request_digest", sa.String(64), nullable=False),
        sa.Column("source", sa.String(40), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("origin_label", sa.String(500), nullable=False),
        sa.Column("destination_label", sa.String(500), nullable=False),
        sa.Column("distance_miles", sa.Float(), nullable=False),
        sa.Column("driving_seconds", sa.Integer(), nullable=False),
        sa.Column("stops", sa.JSON()),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("captured_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.UniqueConstraint("tenant_id", "provider_vehicle_id", "started_at", name="uq_fleet_trip_departure"),
        sa.ForeignKeyConstraint(["tenant_id", "vehicle_id"], ["vehicles.tenant_id", "vehicles.id"]),
        sa.ForeignKeyConstraint(["tenant_id", "fleet_customer_id"], ["customers.tenant_id", "customers.id"]),
        sa.ForeignKeyConstraint(["tenant_id", "vehicle_id", "fleet_customer_id", "fleet_membership_id"], ["fleet_memberships.tenant_id", "fleet_memberships.vehicle_id", "fleet_memberships.fleet_customer_id", "fleet_memberships.id"]),
        sa.CheckConstraint("ended_at > started_at", name="ck_fleet_trip_completed"),
        sa.CheckConstraint("distance_miles >= 0 AND distance_miles <= 100000", name="ck_fleet_trip_distance"),
        sa.CheckConstraint("driving_seconds >= 0 AND driving_seconds <= EXTRACT(EPOCH FROM (ended_at - started_at))", name="ck_fleet_trip_driving"),
        sa.CheckConstraint("driving_seconds >= 0 AND driving_seconds <= 2678400", name="ck_fleet_trip_driving_bound"),
        sa.CheckConstraint("source = 'motive_dashboard_manual'", name="ck_fleet_trip_source"),
    )
    op.create_index("ix_fleet_trips_id", "fleet_trip_snapshots", ["id"])
    op.create_index("ix_fleet_trip_departure", "fleet_trip_snapshots", ["tenant_id", "started_at", "vehicle_id"])


def downgrade():
    op.drop_table("fleet_trip_snapshots")
