"""Reviewed source vehicle identity without fabricating a VIN.

Revision ID: 177_dashboard_bindings
Revises: 176_merge_contact_pricing
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "177_dashboard_bindings"
down_revision = "176_merge_contact_pricing"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "dashboard_vehicle_bindings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
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
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id"),
            nullable=False,
        ),
        sa.Column("vehicle_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("fleet_customer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("fleet_membership_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_company_id", sa.String(120), nullable=False),
        sa.Column("source_company_label", sa.String(255), nullable=False),
        sa.Column("provider_vehicle_id", sa.String(120), nullable=False),
        sa.Column("placeholder_vin", sa.String(17), nullable=False),
        sa.Column(
            "reviewed_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("effective_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column(
            "revoked_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
        ),
        sa.Column("revocation_reason", sa.String(80)),
        sa.Column("revoked_source_vin", sa.String(17)),
        sa.Column("revoked_source_read_at", sa.DateTime(timezone=True)),
        sa.Column("revoked_source_sha256", sa.String(64)),
        sa.Column("review_note", sa.String(1000), nullable=False),
        sa.Column("review_manifest_sha256", sa.String(64), nullable=False),
        sa.Column("source_evidence_sha256", sa.String(64), nullable=False),
        sa.Column(
            "source_evidence_read_at", sa.DateTime(timezone=True), nullable=False
        ),
        sa.Column("source_vin_state", sa.String(30), nullable=False),
        sa.UniqueConstraint(
            "tenant_id",
            "vehicle_id",
            "fleet_membership_id",
            "id",
            name="uq_dashboard_binding_identity",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "vehicle_id"], ["vehicles.tenant_id", "vehicles.id"]
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
        sa.CheckConstraint(
            "effective_from >= reviewed_at AND (effective_to IS NULL OR effective_to > effective_from)",
            name="ck_dashboard_binding_interval",
        ),
    )
    for name, columns in [
        ("vehicle", ["tenant_id", "vehicle_id"]),
        ("provider", ["tenant_id", "source_company_id", "provider_vehicle_id"]),
    ]:
        op.create_index(
            f"uq_dashboard_binding_{name}_active",
            "dashboard_vehicle_bindings",
            columns,
            unique=True,
            postgresql_where=sa.text("revoked_at IS NULL AND deleted_at IS NULL"),
        )
    op.create_index(
        "ix_dashboard_vehicle_bindings_id", "dashboard_vehicle_bindings", ["id"]
    )
    for table, label in [
        ("fleet_driver_record_captures", "driver_record"),
        ("fleet_telemetry_snapshots", "telemetry"),
    ]:
        op.add_column(
            table,
            sa.Column(
                "dashboard_binding_id", postgresql.UUID(as_uuid=True), nullable=True
            ),
        )
        op.alter_column(
            table, "verified_vin", existing_type=sa.String(17), nullable=True
        )
        op.create_foreign_key(
            f"fk_{label}_dashboard_binding",
            table,
            "dashboard_vehicle_bindings",
            ["tenant_id", "vehicle_id", "fleet_membership_id", "dashboard_binding_id"],
            ["tenant_id", "vehicle_id", "fleet_membership_id", "id"],
        )
        op.create_check_constraint(
            f"ck_{label}_identity_basis",
            table,
            "(verified_vin IS NOT NULL AND dashboard_binding_id IS NULL) OR (verified_vin IS NULL AND dashboard_binding_id IS NOT NULL)",
        )


def downgrade():
    bind = op.get_bind()
    if bind.execute(
        sa.text("SELECT EXISTS (SELECT 1 FROM dashboard_vehicle_bindings)")
    ).scalar():
        raise RuntimeError(
            "Reviewed binding history must be retained; revoke binding and keep the guarded application reader"
        )
    for table in ("fleet_driver_record_captures", "fleet_telemetry_snapshots"):
        if bind.execute(
            sa.text(
                f"SELECT EXISTS (SELECT 1 FROM {table} WHERE dashboard_binding_id IS NOT NULL)"
            )
        ).scalar():
            raise RuntimeError(
                "Bound capture history must be retained; revoke binding and keep the guarded application reader"
            )
    for table, label in [
        ("fleet_driver_record_captures", "driver_record"),
        ("fleet_telemetry_snapshots", "telemetry"),
    ]:
        op.drop_constraint(f"ck_{label}_identity_basis", table, type_="check")
        op.drop_constraint(f"fk_{label}_dashboard_binding", table, type_="foreignkey")
        op.alter_column(
            table, "verified_vin", existing_type=sa.String(17), nullable=False
        )
        op.drop_column(table, "dashboard_binding_id")
    op.drop_table("dashboard_vehicle_bindings")
