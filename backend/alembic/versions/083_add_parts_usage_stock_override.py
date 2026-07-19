"""record repair-order stock shortage overrides

Revision ID: 083
Revises: 082
Create Date: 2026-07-19
"""
from alembic import op
import sqlalchemy as sa


revision = "083"
down_revision = "082"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Nullable reservation preserves the historical whole-package behavior for
    # existing rows. New rows always record their actual reservation.
    op.add_column("parts_usage", sa.Column("stock_reserved_packages", sa.Integer(), nullable=True))
    op.add_column(
        "parts_usage",
        sa.Column("stock_shortage_override", sa.Boolean(), server_default=sa.false(), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("parts_usage", "stock_shortage_override")
    op.drop_column("parts_usage", "stock_reserved_packages")
