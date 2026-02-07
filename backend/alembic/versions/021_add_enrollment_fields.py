"""Add enrollment fields to tenants

Revision ID: 021
Revises: 020
Create Date: 2026-02-06

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '021'
down_revision: Union[str, None] = '020'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add enrollment fields to tenants table
    op.execute("""
        ALTER TABLE tenants 
        ADD COLUMN IF NOT EXISTS enrollment_status VARCHAR(20) DEFAULT 'approved' NOT NULL
    """)
    op.execute("""
        ALTER TABLE tenants 
        ADD COLUMN IF NOT EXISTS business_license VARCHAR(100)
    """)
    op.execute("""
        ALTER TABLE tenants 
        ADD COLUMN IF NOT EXISTS ein VARCHAR(20)
    """)
    op.execute("""
        ALTER TABLE tenants 
        ADD COLUMN IF NOT EXISTS website VARCHAR(255)
    """)
    op.execute("""
        ALTER TABLE tenants 
        ADD COLUMN IF NOT EXISTS logo_url VARCHAR(500)
    """)
    op.execute("""
        ALTER TABLE tenants 
        ADD COLUMN IF NOT EXISTS applied_at TIMESTAMP WITH TIME ZONE
    """)
    op.execute("""
        ALTER TABLE tenants 
        ADD COLUMN IF NOT EXISTS approved_at TIMESTAMP WITH TIME ZONE
    """)
    op.execute("""
        ALTER TABLE tenants 
        ADD COLUMN IF NOT EXISTS approved_by_id UUID REFERENCES users(id)
    """)
    op.execute("""
        ALTER TABLE tenants 
        ADD COLUMN IF NOT EXISTS rejection_reason TEXT
    """)


def downgrade() -> None:
    op.drop_column('tenants', 'rejection_reason')
    op.drop_column('tenants', 'approved_by_id')
    op.drop_column('tenants', 'approved_at')
    op.drop_column('tenants', 'applied_at')
    op.drop_column('tenants', 'logo_url')
    op.drop_column('tenants', 'website')
    op.drop_column('tenants', 'ein')
    op.drop_column('tenants', 'business_license')
    op.drop_column('tenants', 'enrollment_status')
