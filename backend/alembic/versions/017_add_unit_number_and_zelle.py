"""Add unit_number to vehicles and zelle info to tenants

Revision ID: 017
Revises: 016
Create Date: 2026-02-06

"""
from alembic import op
import sqlalchemy as sa


revision = '017'
down_revision = '016'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add unit_number to vehicles (index created separately)
    op.add_column('vehicles', sa.Column('unit_number', sa.String(50), nullable=True))
    # Create index if not exists
    op.execute("CREATE INDEX IF NOT EXISTS ix_vehicles_unit_number ON vehicles (unit_number)")
    
    # Add Zelle info to tenants (if not exists)
    op.execute("ALTER TABLE tenants ADD COLUMN IF NOT EXISTS zelle_email VARCHAR(255)")
    op.execute("ALTER TABLE tenants ADD COLUMN IF NOT EXISTS zelle_phone VARCHAR(20)")
    
    # Add 'zelle' to paymentmethod enum
    op.execute("ALTER TYPE paymentmethod ADD VALUE IF NOT EXISTS 'zelle' AFTER 'ach'")


def downgrade() -> None:
    op.drop_index('ix_vehicles_unit_number', 'vehicles')
    op.drop_column('vehicles', 'unit_number')
    op.drop_column('tenants', 'zelle_email')
    op.drop_column('tenants', 'zelle_phone')
    # Note: PostgreSQL doesn't easily support removing enum values
