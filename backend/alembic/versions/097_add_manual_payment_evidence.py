"""add manual payment confirmation evidence

Revision ID: 097_manual_payment_evidence
Revises: 096_invoice_revision_audit
"""
from alembic import op
import sqlalchemy as sa


revision = "097_manual_payment_evidence"
down_revision = "096_invoice_revision_audit"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # PostgreSQL enum additions are intentionally retained on downgrade because
    # removing a value requires rebuilding the enum and can invalidate history.
    op.execute("ALTER TYPE paymentmethod ADD VALUE IF NOT EXISTS 'fleet_payment'")
    op.add_column("payments", sa.Column("payment_provider", sa.String(length=100), nullable=True))
    op.add_column("payments", sa.Column("reference_number", sa.String(length=255), nullable=True))
    op.add_column("payments", sa.Column("authorization_number", sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column("payments", "authorization_number")
    op.drop_column("payments", "reference_number")
    op.drop_column("payments", "payment_provider")
