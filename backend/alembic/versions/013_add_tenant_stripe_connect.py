"""Add Stripe Connect fields to tenants

Revision ID: 013
Revises: 012
Create Date: 2024-01-28

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '013'
down_revision = '012'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('tenants', sa.Column('stripe_account_id', sa.String(255), nullable=True))
    op.add_column('tenants', sa.Column('stripe_onboarding_complete', sa.Boolean(), nullable=False, server_default='false'))
    op.create_index('ix_tenants_stripe_account_id', 'tenants', ['stripe_account_id'], unique=True)


def downgrade() -> None:
    op.drop_index('ix_tenants_stripe_account_id', table_name='tenants')
    op.drop_column('tenants', 'stripe_onboarding_complete')
    op.drop_column('tenants', 'stripe_account_id')
