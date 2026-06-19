"""add fleet inspections, inspection items, and incidents

Revision ID: 048
Revises: 047
Create Date: 2026-06-16
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "048"
down_revision = "047"
branch_labels = None
depends_on = None


inspection_status = postgresql.ENUM(
    "scheduled", "completed", "cancelled", name="inspectionstatus", create_type=False
)
inspection_result = postgresql.ENUM(
    "pass", "attention", "fail", name="inspectionresult", create_type=False
)
inspection_item_result = postgresql.ENUM(
    "pending", "pass", "fail", "na", name="inspectionitemresult", create_type=False
)
incident_severity = postgresql.ENUM(
    "low", "medium", "high", "critical", name="incidentseverity", create_type=False
)
incident_status = postgresql.ENUM(
    "open", "in_progress", "resolved", name="incidentstatus", create_type=False
)


def upgrade() -> None:
    bind = op.get_bind()
    for e in (inspection_status, inspection_result, inspection_item_result,
              incident_severity, incident_status):
        e.create(bind, checkfirst=True)

    op.create_table(
        "fleet_inspections",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("vehicle_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("vehicles.id"), nullable=False),
        sa.Column("inspector_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("status", inspection_status, nullable=False, server_default="scheduled"),
        sa.Column("result", inspection_result, nullable=True),
        sa.Column("scheduled_for", sa.Date(), nullable=False),
        sa.Column("performed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("odometer", sa.Integer(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_fleet_inspections_tenant_id", "fleet_inspections", ["tenant_id"])
    op.create_index("ix_fleet_inspections_vehicle_id", "fleet_inspections", ["vehicle_id"])
    op.create_index("ix_fleet_inspections_status", "fleet_inspections", ["status"])
    op.create_index("ix_fleet_inspections_scheduled_for", "fleet_inspections", ["scheduled_for"])

    op.create_table(
        "fleet_inspection_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("inspection_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("fleet_inspections.id"), nullable=False),
        sa.Column("category", sa.String(length=80), nullable=False),
        sa.Column("label", sa.String(length=160), nullable=False),
        sa.Column("result", inspection_item_result, nullable=False, server_default="pending"),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_fleet_inspection_items_tenant_id", "fleet_inspection_items", ["tenant_id"])
    op.create_index("ix_fleet_inspection_items_inspection_id", "fleet_inspection_items", ["inspection_id"])

    op.create_table(
        "fleet_incidents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("vehicle_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("vehicles.id"), nullable=False),
        sa.Column("reported_by_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("location", sa.String(length=255), nullable=True),
        sa.Column("severity", incident_severity, nullable=False, server_default="medium"),
        sa.Column("status", incident_status, nullable=False, server_default="open"),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("resolution_notes", sa.Text(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("repair_order_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("repair_orders.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_fleet_incidents_tenant_id", "fleet_incidents", ["tenant_id"])
    op.create_index("ix_fleet_incidents_vehicle_id", "fleet_incidents", ["vehicle_id"])
    op.create_index("ix_fleet_incidents_severity", "fleet_incidents", ["severity"])
    op.create_index("ix_fleet_incidents_status", "fleet_incidents", ["status"])
    op.create_index("ix_fleet_incidents_repair_order_id", "fleet_incidents", ["repair_order_id"])


def downgrade() -> None:
    op.drop_table("fleet_incidents")
    op.drop_table("fleet_inspection_items")
    op.drop_table("fleet_inspections")
    for name in ("incidentstatus", "incidentseverity", "inspectionitemresult",
                 "inspectionresult", "inspectionstatus"):
        op.execute(f"DROP TYPE IF EXISTS {name}")
