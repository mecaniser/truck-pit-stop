"""Add invoice reminder tracking fields

Revision ID: 018
Revises: 017
Create Date: 2026-02-06

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '018'
down_revision = '017'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add reminder tracking columns to invoices
    op.execute("ALTER TABLE invoices ADD COLUMN IF NOT EXISTS last_reminder_sent_at TIMESTAMP WITH TIME ZONE")
    op.execute("ALTER TABLE invoices ADD COLUMN IF NOT EXISTS reminder_count INTEGER DEFAULT 0 NOT NULL")


def downgrade() -> None:
    op.drop_column('invoices', 'reminder_count')
    op.drop_column('invoices', 'last_reminder_sent_at')
