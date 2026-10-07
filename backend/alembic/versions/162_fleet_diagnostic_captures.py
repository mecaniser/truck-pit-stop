"""Immutable dashboard diagnostic observations without OAuth lifecycle inference."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "162_fleet_diagnostic_captures"
down_revision = "161_telemetry_observed_precision"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "fleet_diagnostic_captures",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.Column(
            "tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False
        ),
        sa.Column("vehicle_id", UUID(as_uuid=True), nullable=False),
        sa.Column("fleet_customer_id", UUID(as_uuid=True), nullable=False),
        sa.Column("fleet_membership_id", UUID(as_uuid=True), nullable=False),
        sa.Column("verified_vin", sa.String(17), nullable=False),
        sa.Column("provider_vehicle_id", sa.String(120), nullable=False),
        sa.Column("source_company_id", sa.String(120), nullable=False),
        sa.Column("source_company_label", sa.String(255), nullable=False),
        sa.Column("source", sa.String(40), nullable=False),
        sa.Column("source_read_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "captured_by_user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("client_request_id", UUID(as_uuid=True), nullable=False),
        sa.Column("content_sha256", sa.String(64), nullable=False),
        sa.Column("coverage", sa.String(20), nullable=False),
        sa.Column("explicit_empty", sa.Boolean, nullable=False),
        sa.Column("source_scope", sa.String(80), nullable=False),
        sa.Column("codes", sa.JSON, nullable=False),
        sa.UniqueConstraint(
            "tenant_id", "client_request_id", name="uq_diagnostic_capture_request"
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "vehicle_id"], ["vehicles.tenant_id", "vehicles.id"]
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "fleet_customer_id"], ["customers.tenant_id", "customers.id"]
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "vehicle_id", "fleet_customer_id", "fleet_membership_id"],
            [
                "fleet_memberships.tenant_id",
                "fleet_memberships.vehicle_id",
                "fleet_memberships.fleet_customer_id",
                "fleet_memberships.id",
            ],
        ),
        sa.CheckConstraint("source = 'motive_dashboard'", name="ck_diagnostic_source"),
        sa.CheckConstraint("coverage = 'complete'", name="ck_diagnostic_coverage"),
        sa.CheckConstraint(
            "source_scope = 'Current fault codes'", name="ck_diagnostic_scope"
        ),
        sa.CheckConstraint(
            "source_read_at <= captured_at", name="ck_diagnostic_read_time"
        ),
        sa.CheckConstraint(
            "json_typeof(codes) = 'array' AND ((explicit_empty AND json_array_length(codes) = 0) OR (NOT explicit_empty AND json_array_length(codes) > 0))",
            name="ck_diagnostic_explicit_empty",
        ),
    )
    op.create_index(
        "ix_fleet_diagnostic_captures_id", "fleet_diagnostic_captures", ["id"]
    )
    op.create_index(
        "ix_diagnostic_vehicle_read",
        "fleet_diagnostic_captures",
        ["tenant_id", "vehicle_id", "source_read_at"],
    )


def downgrade():
    op.execute(
        "DO $$ BEGIN IF EXISTS (SELECT 1 FROM fleet_diagnostic_captures) THEN RAISE EXCEPTION 'Retain revision 162: diagnostic observations exist'; END IF; END $$"
    )
    op.drop_table("fleet_diagnostic_captures")
