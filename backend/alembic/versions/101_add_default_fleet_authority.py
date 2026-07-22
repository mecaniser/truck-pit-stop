"""add configurable default Fleet Board authority

Revision ID: 101_default_fleet_authority
Revises: 100_merge_invoice_vehicle_heads
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "101_default_fleet_authority"
down_revision = "100_merge_invoice_vehicle_heads"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tenants",
        sa.Column("default_fleet_authority_customer_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_tenants_default_fleet_authority_customer",
        "tenants",
        "customers",
        ["default_fleet_authority_customer_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_tenants_default_fleet_authority_customer_id",
        "tenants",
        ["default_fleet_authority_customer_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_tenants_default_fleet_authority_customer_id", table_name="tenants")
    op.drop_constraint("fk_tenants_default_fleet_authority_customer", "tenants", type_="foreignkey")
    op.drop_column("tenants", "default_fleet_authority_customer_id")
