"""Add source field to customers

Revision ID: 028
Revises: 027
Create Date: 2026-02-12
"""
from alembic import op
import sqlalchemy as sa


revision = "028"
down_revision = "027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("customers", sa.Column("source", sa.String(length=50), nullable=True))
    op.create_index("ix_customers_source", "customers", ["source"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_customers_source", table_name="customers")
    op.drop_column("customers", "source")
