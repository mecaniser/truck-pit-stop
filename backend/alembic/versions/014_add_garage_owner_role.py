"""Add GARAGE_OWNER role and tenant ownership

Revision ID: 014
Revises: 013
Create Date: 2026-01-31

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '014'
down_revision = '013'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add GARAGE_OWNER to the UserRole enum
    op.execute("ALTER TYPE userrole ADD VALUE 'garage_owner'")
    
    # Add owner_id column to tenants table
    op.add_column('tenants', sa.Column('owner_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.create_index('ix_tenants_owner_id', 'tenants', ['owner_id'], unique=False)
    op.create_foreign_key('fk_tenants_owner_id', 'tenants', 'users', ['owner_id'], ['id'])


def downgrade() -> None:
    # Drop foreign key and column
    op.drop_constraint('fk_tenants_owner_id', 'tenants', type_='foreignkey')
    op.drop_index('ix_tenants_owner_id', table_name='tenants')
    op.drop_column('tenants', 'owner_id')
    
    # Note: PostgreSQL doesn't support removing enum values directly
    # You would need to recreate the enum type to remove 'garage_owner'
    # This is left as a manual operation if downgrade is needed
