"""Add work timestamps to repair_orders and auto_approval_threshold to customers

Revision ID: 015
Revises: 014
Create Date: 2026-02-06

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '015'
down_revision = '014'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Per-job time tracking: record when work actually starts and completes
    op.add_column('repair_orders', sa.Column('work_started_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('repair_orders', sa.Column('work_completed_at', sa.DateTime(timezone=True), nullable=True))

    # Auto-approval threshold: fleet customers can pre-authorize repairs under $X
    op.add_column('customers', sa.Column('auto_approval_threshold', sa.Numeric(10, 2), nullable=True))


def downgrade() -> None:
    op.drop_column('customers', 'auto_approval_threshold')
    op.drop_column('repair_orders', 'work_completed_at')
    op.drop_column('repair_orders', 'work_started_at')
