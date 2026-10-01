"""Immutable fleet dashboard observations.
Revision ID: 154
Revises: 153
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "154_fleet_telemetry_snapshots"
down_revision = "153_motive_full_scope"
branch_labels = None
depends_on = None


def upgrade():
    op.create_unique_constraint(
        "uq_membership_telemetry_identity",
        "fleet_memberships",
        ["tenant_id", "vehicle_id", "fleet_customer_id", "id"],
    )
    cols = [
        sa.Column(n, postgresql.UUID(as_uuid=True), nullable=False)
        for n in (
            "id",
            "tenant_id",
            "vehicle_id",
            "fleet_customer_id",
            "fleet_membership_id",
            "client_request_id",
            "captured_by_user_id",
        )
    ]
    cols += [
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True)),
    ]
    cols += [
        sa.Column(n, sa.String(l), nullable=nullable)
        for n, l, nullable in [
            ("verified_vin", 17, False),
            ("request_digest", 64, False),
            ("source", 40, False),
            ("source_age_text", 120, True),
            ("provider_company_label", 255, True),
            ("provider_vehicle_id", 120, True),
            ("provider_vehicle_number", 120, True),
            ("location_label", 500, True),
            ("evidence_note", 1000, True),
        ]
    ]
    cols += [
        sa.Column(n, sa.Float())
        for n in (
            "lat",
            "lng",
            "speed_mph",
            "odometer_miles",
            "engine_hours",
            "fuel_percent",
        )
    ]
    op.create_table(
        "fleet_telemetry_snapshots",
        *cols,
        sa.Column("fault_count", sa.Integer()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id", "client_request_id", name="uq_telemetry_request"
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["captured_by_user_id"], ["users.id"]),
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
    )
    op.create_index(
        "ix_telemetry_vehicle_capture",
        "fleet_telemetry_snapshots",
        ["tenant_id", "vehicle_id", "captured_at"],
    )
    op.create_index(
        "ix_telemetry_retention", "fleet_telemetry_snapshots", ["captured_at"]
    )
    op.create_index(
        "ix_fleet_telemetry_snapshots_id", "fleet_telemetry_snapshots", ["id"]
    )


def downgrade():
    op.drop_table("fleet_telemetry_snapshots")
    op.drop_constraint(
        "uq_membership_telemetry_identity", "fleet_memberships", type_="unique"
    )
