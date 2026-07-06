"""add labor + order dollar discounts to repair orders

Revision ID: 059
Revises: 058
Create Date: 2026-06-20
"""
from alembic import op
import sqlalchemy as sa


revision = "059"
down_revision = "058"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("repair_orders", sa.Column("labor_discount_amount", sa.Numeric(10, 2), nullable=False, server_default="0.00"))
    op.add_column("repair_orders", sa.Column("order_discount_amount", sa.Numeric(10, 2), nullable=False, server_default="0.00"))
    op.alter_column("repair_orders", "labor_discount_amount", server_default=None)
    op.alter_column("repair_orders", "order_discount_amount", server_default=None)


def downgrade() -> None:
    op.drop_column("repair_orders", "order_discount_amount")
    op.drop_column("repair_orders", "labor_discount_amount")
