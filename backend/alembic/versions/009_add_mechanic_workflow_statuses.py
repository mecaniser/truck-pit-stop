"""Add mechanic workflow statuses

Revision ID: 009
Revises: 008
Create Date: 2026-01-29
"""
from alembic import op


revision = "009"
down_revision = "008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add new enum values to repair_order_status
    # PostgreSQL requires ALTER TYPE to add enum values
    op.execute("ALTER TYPE repairorderstatus ADD VALUE IF NOT EXISTS 'assigned'")
    op.execute("ALTER TYPE repairorderstatus ADD VALUE IF NOT EXISTS 'acknowledged'")
    op.execute("ALTER TYPE repairorderstatus ADD VALUE IF NOT EXISTS 'pending_review'")


def downgrade() -> None:
    # PostgreSQL doesn't support removing enum values easily
    # Would need to recreate the type and migrate data
    pass
