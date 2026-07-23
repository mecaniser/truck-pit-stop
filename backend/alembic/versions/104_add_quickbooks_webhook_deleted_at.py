"""add soft-delete column to QuickBooks webhook events

Revision ID: 104_qb_webhook_deleted_at
Revises: 103_quickbooks_cdc
"""

from alembic import op
import sqlalchemy as sa


revision = "104_qb_webhook_deleted_at"
down_revision = "103_quickbooks_cdc"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "quickbooks_webhook_events",
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("quickbooks_webhook_events", "deleted_at")
