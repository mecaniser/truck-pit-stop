"""add QuickBooks connection health fields

Revision ID: 089
Revises: 088
"""
from alembic import op
import sqlalchemy as sa


revision = "089"
down_revision = "088"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("quickbooks_connections", sa.Column("last_token_refresh_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("quickbooks_connections", sa.Column("last_token_refresh_error", sa.Text(), nullable=True))
    op.add_column("quickbooks_connections", sa.Column("last_webhook_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("quickbooks_connections", sa.Column("last_webhook_event", sa.String(length=160), nullable=True))
    op.add_column("quickbooks_connections", sa.Column("last_webhook_error", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("quickbooks_connections", "last_webhook_error")
    op.drop_column("quickbooks_connections", "last_webhook_event")
    op.drop_column("quickbooks_connections", "last_webhook_at")
    op.drop_column("quickbooks_connections", "last_token_refresh_error")
    op.drop_column("quickbooks_connections", "last_token_refresh_at")
