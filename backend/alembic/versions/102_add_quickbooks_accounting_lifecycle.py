"""add QuickBooks accounting lifecycle and reconciliation fields

Revision ID: 102_quickbooks_lifecycle
Revises: 101_default_fleet_authority
"""
from alembic import op
import sqlalchemy as sa


revision = "102_quickbooks_lifecycle"
down_revision = "101_default_fleet_authority"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("invoices", sa.Column("quickbooks_invoice_id", sa.String(length=64), nullable=True))
    op.add_column("invoices", sa.Column("quickbooks_sync_status", sa.String(length=32), nullable=False, server_default="pending"))
    op.add_column("invoices", sa.Column("quickbooks_synced_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("invoices", sa.Column("quickbooks_sync_error", sa.Text(), nullable=True))
    op.create_index("ix_invoices_quickbooks_invoice_id", "invoices", ["quickbooks_invoice_id"])
    op.create_index("ix_invoices_quickbooks_sync_status", "invoices", ["quickbooks_sync_status"])

    op.add_column("payments", sa.Column("quickbooks_payment_id", sa.String(length=64), nullable=True))
    op.add_column("payments", sa.Column("quickbooks_refund_id", sa.String(length=255), nullable=True))
    op.add_column("payments", sa.Column("quickbooks_refund_receipt_id", sa.String(length=64), nullable=True))
    op.add_column("payments", sa.Column("quickbooks_refunded_amount", sa.Numeric(10, 2), nullable=True))
    op.add_column("payments", sa.Column("quickbooks_reconciled_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("payments", sa.Column("quickbooks_sync_error", sa.Text(), nullable=True))
    op.create_index("ix_payments_quickbooks_payment_id", "payments", ["quickbooks_payment_id"])
    op.create_index("ix_payments_quickbooks_refund_id", "payments", ["quickbooks_refund_id"], unique=True)
    op.create_index("ix_payments_quickbooks_refund_receipt_id", "payments", ["quickbooks_refund_receipt_id"])

    op.create_table(
        "quickbooks_webhook_events",
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("realm_id", sa.String(length=64), nullable=False),
        sa.Column("entity_name", sa.String(length=64), nullable=False),
        sa.Column("entity_id", sa.String(length=64), nullable=False),
        sa.Column("operation", sa.String(length=32), nullable=False),
        sa.Column("last_updated_at", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "realm_id", "entity_name", "entity_id", "operation", "last_updated_at",
            name="uq_quickbooks_webhook_delivery",
        ),
    )
    op.create_index("ix_quickbooks_webhook_events_tenant_id", "quickbooks_webhook_events", ["tenant_id"])
    op.create_index("ix_quickbooks_webhook_events_realm_id", "quickbooks_webhook_events", ["realm_id"])
    op.create_index("ix_quickbooks_webhook_events_status", "quickbooks_webhook_events", ["status"])


def downgrade() -> None:
    op.drop_table("quickbooks_webhook_events")
    for name in (
        "ix_payments_quickbooks_refund_receipt_id",
        "ix_payments_quickbooks_refund_id",
        "ix_payments_quickbooks_payment_id",
    ):
        op.drop_index(name, table_name="payments")
    for column in (
        "quickbooks_sync_error",
        "quickbooks_reconciled_at",
        "quickbooks_refunded_amount",
        "quickbooks_refund_receipt_id",
        "quickbooks_refund_id",
        "quickbooks_payment_id",
    ):
        op.drop_column("payments", column)
    op.drop_index("ix_invoices_quickbooks_sync_status", table_name="invoices")
    op.drop_index("ix_invoices_quickbooks_invoice_id", table_name="invoices")
    for column in (
        "quickbooks_sync_error",
        "quickbooks_synced_at",
        "quickbooks_sync_status",
        "quickbooks_invoice_id",
    ):
        op.drop_column("invoices", column)
