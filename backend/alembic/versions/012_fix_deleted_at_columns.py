"""Add missing deleted_at columns

Revision ID: 012
Revises: 011
Create Date: 2026-01-30
"""
from alembic import op

revision = "012"
down_revision = "011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add deleted_at to mechanic_points if missing
    op.execute("""
        ALTER TABLE mechanic_points 
        ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMP WITH TIME ZONE
    """)
    
    # Add deleted_at to mechanic_points_balance if missing
    op.execute("""
        ALTER TABLE mechanic_points_balance 
        ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMP WITH TIME ZONE
    """)
    
    # Add deleted_at to pto_requests if missing
    op.execute("""
        ALTER TABLE pto_requests 
        ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMP WITH TIME ZONE
    """)


def downgrade() -> None:
    pass  # Don't remove columns on downgrade
