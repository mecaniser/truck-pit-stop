"""add list_price snapshot to parts_usage for savings audit trail

Revision ID: 046
Revises: 045
Create Date: 2026-04-22
"""
from alembic import op
import sqlalchemy as sa


revision = "046"
down_revision = "045"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "parts_usage",
        sa.Column("list_price", sa.Numeric(10, 2), nullable=True),
    )
    # Backfill existing rows so savings=0 for anything attached before this change.
    op.execute("UPDATE parts_usage SET list_price = unit_price WHERE list_price IS NULL")


def downgrade() -> None:
    op.drop_column("parts_usage", "list_price")
