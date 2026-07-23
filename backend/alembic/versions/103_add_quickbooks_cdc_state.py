"""add QuickBooks Change Data Capture cursor state

Revision ID: 103_quickbooks_cdc
Revises: 102_quickbooks_lifecycle
"""
from alembic import op
import sqlalchemy as sa


revision = "103_quickbooks_cdc"
down_revision = "102_quickbooks_lifecycle"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("quickbooks_connections", sa.Column("last_cdc_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("quickbooks_connections", sa.Column("last_cdc_error", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("quickbooks_connections", "last_cdc_error")
    op.drop_column("quickbooks_connections", "last_cdc_at")
