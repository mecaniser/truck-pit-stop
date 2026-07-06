"""add vehicle_pm_services and repair_order_pm_services

Service-based preventive maintenance. A truck carries a saved default PM service
package (vehicle_pm_services); scheduling a PM copies it onto the work order
(repair_order_pm_services), where it drives the manager-facing scope and the
owner-facing seeded labor/parts cost lines.

Revision ID: 057
Revises: 056
Create Date: 2026-07-04
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision = "057"
down_revision = "056"
branch_labels = None
depends_on = None


def _pm_service_table(name: str, owner_col: str, owner_fk: str) -> None:
    op.create_table(
        name,
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column(owner_col, UUID(as_uuid=True), sa.ForeignKey(owner_fk), nullable=False),
        sa.Column("service_id", UUID(as_uuid=True), sa.ForeignKey("services.id"), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index(f"ix_{name}_tenant_id", name, ["tenant_id"])
    op.create_index(f"ix_{name}_{owner_col}", name, [owner_col])
    op.create_index(f"ix_{name}_service_id", name, ["service_id"])


def upgrade() -> None:
    _pm_service_table("vehicle_pm_services", "vehicle_id", "vehicles.id")
    _pm_service_table("repair_order_pm_services", "repair_order_id", "repair_orders.id")


def downgrade() -> None:
    op.drop_table("repair_order_pm_services")
    op.drop_table("vehicle_pm_services")
