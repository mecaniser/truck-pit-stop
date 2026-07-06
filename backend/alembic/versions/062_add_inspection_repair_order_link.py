"""add fleet_inspections.repair_order_id

Links an inspection to the work order created to fix its failed items, for
traceability (inspection defect -> repair).

Revision ID: 062
Revises: 061
Create Date: 2026-07-01
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "062"
down_revision = "061"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "fleet_inspections",
        sa.Column("repair_order_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_fleet_inspections_repair_order",
        "fleet_inspections", "repair_orders",
        ["repair_order_id"], ["id"],
    )


def downgrade() -> None:
    op.drop_constraint("fk_fleet_inspections_repair_order", "fleet_inspections", type_="foreignkey")
    op.drop_column("fleet_inspections", "repair_order_id")
