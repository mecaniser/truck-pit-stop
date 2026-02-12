"""Add company_name to customers

Revision ID: 029
Revises: 028
Create Date: 2026-02-12
"""
from alembic import op
import sqlalchemy as sa


revision = "029"
down_revision = "028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("customers", sa.Column("company_name", sa.String(length=255), nullable=True))
    op.create_index("ix_customers_company_name", "customers", ["company_name"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_customers_company_name", table_name="customers")
    op.drop_column("customers", "company_name")
