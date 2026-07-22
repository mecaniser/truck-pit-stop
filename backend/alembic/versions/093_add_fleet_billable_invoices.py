"""add billable fleet invoice contacts and labor pricing

Revision ID: 093_fleet_billable_invoices
Revises: 092_fleet_board_read_model
"""
from alembic import op
import sqlalchemy as sa


revision = "093_fleet_billable_invoices"
down_revision = "092_fleet_board_read_model"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("vehicles", sa.Column("billing_contact_name", sa.String(length=160), nullable=True))
    op.add_column("vehicles", sa.Column("billing_contact_email", sa.String(length=255), nullable=True))
    op.add_column("vehicles", sa.Column("billing_contact_phone", sa.String(length=20), nullable=True))
    op.add_column(
        "vehicles",
        sa.Column("bill_labor_at_customer_rate", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "repair_orders",
        sa.Column("bill_labor_at_customer_rate", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column("invoices", sa.Column("recipient_name", sa.String(length=160), nullable=True))
    op.add_column("invoices", sa.Column("recipient_email", sa.String(length=255), nullable=True))
    op.add_column("invoices", sa.Column("recipient_phone", sa.String(length=20), nullable=True))


def downgrade() -> None:
    op.drop_column("invoices", "recipient_phone")
    op.drop_column("invoices", "recipient_email")
    op.drop_column("invoices", "recipient_name")
    op.drop_column("repair_orders", "bill_labor_at_customer_rate")
    op.drop_column("vehicles", "bill_labor_at_customer_rate")
    op.drop_column("vehicles", "billing_contact_phone")
    op.drop_column("vehicles", "billing_contact_email")
    op.drop_column("vehicles", "billing_contact_name")
