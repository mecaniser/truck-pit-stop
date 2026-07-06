"""add inventory.unit_type and switch part quantity to decimal

Revision ID: 064
Revises: 063

Fluids (oil, coolant, DEF) are dispensed in fractional amounts (e.g. 1.25
gallons), unlike discrete parts (filters, belts) which are always whole
units. This adds Inventory.unit_type so the Price Builder knows which
parts should offer quarter-increment quantities, and widens
PartsUsage.quantity / ServicePart.quantity from integer to numeric so
those fractional amounts can actually be stored and priced.
"""
from alembic import op
import sqlalchemy as sa


revision = "064"
down_revision = "063"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "inventory",
        sa.Column("unit_type", sa.String(length=20), nullable=False, server_default="each"),
    )
    op.alter_column(
        "parts_usage",
        "quantity",
        type_=sa.Numeric(6, 2),
        existing_type=sa.Integer(),
        postgresql_using="quantity::numeric(6,2)",
    )
    op.alter_column(
        "service_parts",
        "quantity",
        type_=sa.Numeric(6, 2),
        existing_type=sa.Integer(),
        postgresql_using="quantity::numeric(6,2)",
    )


def downgrade() -> None:
    op.alter_column(
        "service_parts",
        "quantity",
        type_=sa.Integer(),
        existing_type=sa.Numeric(6, 2),
        postgresql_using="round(quantity)::integer",
    )
    op.alter_column(
        "parts_usage",
        "quantity",
        type_=sa.Integer(),
        existing_type=sa.Numeric(6, 2),
        postgresql_using="round(quantity)::integer",
    )
    op.drop_column("inventory", "unit_type")
