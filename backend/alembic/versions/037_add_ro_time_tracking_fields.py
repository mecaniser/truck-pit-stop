"""add RO time tracking and transition timestamp fields

Revision ID: 037
Revises: 036
"""
from alembic import op
import sqlalchemy as sa

revision = "037"
down_revision = "036"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("repair_orders", sa.Column("estimated_labor_minutes", sa.Integer(), nullable=True))
    op.add_column("repair_orders", sa.Column("actual_tracked_minutes", sa.Integer(), nullable=True))
    op.add_column("repair_orders", sa.Column("total_hold_minutes", sa.Integer(), nullable=True))
    op.add_column("repair_orders", sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("repair_orders", sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("repair_orders", "acknowledged_at")
    op.drop_column("repair_orders", "assigned_at")
    op.drop_column("repair_orders", "total_hold_minutes")
    op.drop_column("repair_orders", "actual_tracked_minutes")
    op.drop_column("repair_orders", "estimated_labor_minutes")
