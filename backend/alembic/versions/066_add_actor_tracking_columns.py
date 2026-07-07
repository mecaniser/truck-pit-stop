"""add actor tracking columns to quotes, invoices, payments

The staff member who sends a quote, creates an invoice, or records a
payment is available in the request at write time but was never saved —
so there was no way to show "by Jane" for these actions. This adds one
nullable actor column to each table, following the same pattern as
repair_orders.cancelled_by_user_id / deleted_by_user_id. Customer/guest
self-service paths (Stripe confirmation, guest checkout) have no staff
actor and leave the column null.

Revision ID: 066
Revises: 065
Create Date: 2026-07-07
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "066"
down_revision = "065"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "quotes",
        sa.Column("sent_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
    )
    op.add_column(
        "invoices",
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
    )
    op.add_column(
        "payments",
        sa.Column("recorded_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("payments", "recorded_by_user_id")
    op.drop_column("invoices", "created_by_user_id")
    op.drop_column("quotes", "sent_by_user_id")
