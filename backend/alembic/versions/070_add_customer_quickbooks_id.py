"""add quickbooks_customer_id to customers

QuickBooks integration is planned but not yet built. Adding the column now so
the "QuickBooks: Linked / Not linked" status can be surfaced on the customer
detail page today (as "Not linked" for everyone) and populated later once the
actual sync exists, without another migration.

Revision ID: 070
Revises: 069
Create Date: 2026-07-08
"""
from alembic import op
import sqlalchemy as sa


revision = "070"
down_revision = "069"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("customers", sa.Column("quickbooks_customer_id", sa.String(255), nullable=True))
    op.create_unique_constraint("uq_customers_quickbooks_customer_id", "customers", ["quickbooks_customer_id"])


def downgrade() -> None:
    op.drop_constraint("uq_customers_quickbooks_customer_id", "customers", type_="unique")
    op.drop_column("customers", "quickbooks_customer_id")
