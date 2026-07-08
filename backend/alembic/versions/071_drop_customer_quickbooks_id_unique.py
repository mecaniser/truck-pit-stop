"""drop unique constraint on customers.quickbooks_customer_id

Migration 070 added this column with a UNIQUE constraint mirroring
stripe_customer_id, but that's premature: without the real QuickBooks
integration built yet, we only have a placeholder "linked/not linked" marker
(not a real per-customer QB id), and hundreds of customers legitimately share
the same placeholder value. Once real sync exists and populates actual QB
customer IDs, those will naturally be unique — re-add the constraint then if
still desired.

Revision ID: 071
Revises: 070
Create Date: 2026-07-08
"""
from alembic import op


revision = "071"
down_revision = "070"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("uq_customers_quickbooks_customer_id", "customers", type_="unique")


def downgrade() -> None:
    op.create_unique_constraint("uq_customers_quickbooks_customer_id", "customers", ["quickbooks_customer_id"])
