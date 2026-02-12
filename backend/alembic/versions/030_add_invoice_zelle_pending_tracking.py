"""Add invoice zelle pending confirmation tracking

Revision ID: 030
Revises: 029
Create Date: 2026-02-12
"""
from alembic import op
import sqlalchemy as sa


revision = "030"
down_revision = "029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("invoices", sa.Column("zelle_pending_submitted_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("invoices", sa.Column("zelle_pending_sender_email", sa.String(length=255), nullable=True))
    op.add_column("invoices", sa.Column("zelle_pending_sender_phone", sa.String(length=20), nullable=True))
    op.add_column("invoices", sa.Column("zelle_pending_last_reminder_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("invoices", sa.Column("zelle_pending_reminder_count", sa.Integer(), nullable=False, server_default="0"))
    op.create_index("ix_invoices_zelle_pending_submitted_at", "invoices", ["zelle_pending_submitted_at"], unique=False)
    op.alter_column("invoices", "zelle_pending_reminder_count", server_default=None)


def downgrade() -> None:
    op.drop_index("ix_invoices_zelle_pending_submitted_at", table_name="invoices")
    op.drop_column("invoices", "zelle_pending_reminder_count")
    op.drop_column("invoices", "zelle_pending_last_reminder_at")
    op.drop_column("invoices", "zelle_pending_sender_phone")
    op.drop_column("invoices", "zelle_pending_sender_email")
    op.drop_column("invoices", "zelle_pending_submitted_at")
