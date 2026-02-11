"""Add unit_cost snapshot to parts_usage

Revision ID: 026
Revises: 025
Create Date: 2026-02-10
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers
revision = "026"
down_revision = "025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("parts_usage", sa.Column("unit_cost", sa.Numeric(10, 2), nullable=True))

    # Backfill historical rows from current inventory cost where possible.
    op.execute(
        """
        UPDATE parts_usage pu
        SET unit_cost = i.cost
        FROM inventory i
        WHERE pu.inventory_id = i.id
          AND pu.unit_cost IS NULL
        """
    )


def downgrade() -> None:
    op.drop_column("parts_usage", "unit_cost")
