"""add tenants.order_number_prefix

Repair order numbers were generated with a hardcoded "RO-" prefix regardless
of shop name. Adds a per-tenant override so each shop can brand its own
repair order numbers (e.g. "TPS-..." for Truck Pit Stop). Nullable — when
unset, the app auto-derives a prefix from the shop name at generation time.

Revision ID: 072
Revises: 071
Create Date: 2026-07-09
"""
from alembic import op
import sqlalchemy as sa


revision = "072"
down_revision = "071"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tenants", sa.Column("order_number_prefix", sa.String(length=10), nullable=True))


def downgrade() -> None:
    op.drop_column("tenants", "order_number_prefix")
