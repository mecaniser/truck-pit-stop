"""add repair order hold fields

Revision ID: 034
Revises: 033
"""
from alembic import op
import sqlalchemy as sa

revision = "034"
down_revision = "033"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("repair_orders", sa.Column("hold_reason", sa.String(100), nullable=True))
    op.add_column("repair_orders", sa.Column("held_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("repair_orders", "held_at")
    op.drop_column("repair_orders", "hold_reason")
