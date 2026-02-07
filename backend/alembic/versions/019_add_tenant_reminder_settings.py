"""Add tenant invoice reminder settings

Revision ID: 019
Revises: 018
Create Date: 2026-02-06

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '019'
down_revision: Union[str, None] = '018'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add tenant-controlled invoice reminder settings
    # Using IF NOT EXISTS for idempotency
    op.execute("""
        ALTER TABLE tenants 
        ADD COLUMN IF NOT EXISTS invoice_reminders_enabled BOOLEAN DEFAULT TRUE NOT NULL
    """)
    op.execute("""
        ALTER TABLE tenants 
        ADD COLUMN IF NOT EXISTS reminder_frequency_days INTEGER DEFAULT 3 NOT NULL
    """)
    op.execute("""
        ALTER TABLE tenants 
        ADD COLUMN IF NOT EXISTS max_invoice_reminders INTEGER DEFAULT 3 NOT NULL
    """)


def downgrade() -> None:
    op.drop_column('tenants', 'max_invoice_reminders')
    op.drop_column('tenants', 'reminder_frequency_days')
    op.drop_column('tenants', 'invoice_reminders_enabled')
