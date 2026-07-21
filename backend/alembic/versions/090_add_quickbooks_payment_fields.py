"""add QuickBooks Payments provider fields

Revision ID: 090
Revises: 089
"""
from alembic import op
import sqlalchemy as sa


revision = "090"
down_revision = "089"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE paymentmethod ADD VALUE IF NOT EXISTS 'quickbooks'")
    op.add_column("payments", sa.Column("quickbooks_charge_id", sa.String(length=255), nullable=True))
    op.add_column("payments", sa.Column("quickbooks_charge_status", sa.String(length=50), nullable=True))
    op.add_column("payments", sa.Column("quickbooks_idempotency_key", sa.String(length=64), nullable=True))
    op.create_index(op.f("ix_payments_quickbooks_charge_id"), "payments", ["quickbooks_charge_id"], unique=True)
    op.create_index(op.f("ix_payments_quickbooks_charge_status"), "payments", ["quickbooks_charge_status"], unique=False)
    op.create_index(op.f("ix_payments_quickbooks_idempotency_key"), "payments", ["quickbooks_idempotency_key"], unique=True)


def downgrade() -> None:
    op.drop_index(op.f("ix_payments_quickbooks_idempotency_key"), table_name="payments")
    op.drop_index(op.f("ix_payments_quickbooks_charge_status"), table_name="payments")
    op.drop_index(op.f("ix_payments_quickbooks_charge_id"), table_name="payments")
    op.drop_column("payments", "quickbooks_idempotency_key")
    op.drop_column("payments", "quickbooks_charge_status")
    op.drop_column("payments", "quickbooks_charge_id")
    # PostgreSQL cannot safely remove an enum value while rows/history may use it.
