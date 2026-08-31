"""Record whether a repair order's intake mileage was read or carried forward.

An odometer reading that was reused from the previous visit is not a reading of
this visit. Left indistinguishable, a service interval computed from it silently
treats stale miles as current, and nobody downstream can tell which rows were
actually observed.

Revision ID: 129_repair_order_mileage_carried
Revises: 128_inventory_lifecycle_v11
"""
from alembic import op
import sqlalchemy as sa

revision = "129_repair_order_mileage_carried"
down_revision = "128_inventory_lifecycle_v11"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "repair_orders",
        sa.Column(
            "mileage_in_carried",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("repair_orders", "mileage_in_carried")
