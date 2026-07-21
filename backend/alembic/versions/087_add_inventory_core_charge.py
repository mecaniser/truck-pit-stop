"""add core_charge to inventory for core-value tracking

A "core charge" is a refundable deposit on rebuildable parts (alternators,
starters, turbos, injectors, etc.) — the customer pays it and gets it back when
the old core is returned. Tracking it lets the inventory valuation report split
Part Value (cost x qty) from Core Value (core_charge x qty), matching how shop
platforms like Easy Truck Shop present inventory worth.

Defaults to 0.00 so existing parts (which carry no core charge) are unaffected.

Revision ID: 087
Revises: 086
Create Date: 2026-07-20
"""
from decimal import Decimal

from alembic import op
import sqlalchemy as sa


revision = "087"
down_revision = "086"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "inventory",
        sa.Column("core_charge", sa.Numeric(10, 2), nullable=False, server_default="0.00"),
    )


def downgrade() -> None:
    op.drop_column("inventory", "core_charge")
