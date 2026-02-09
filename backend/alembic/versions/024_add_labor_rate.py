"""Add labor_rate to tenants

Revision ID: 024
Revises: 023
Create Date: 2026-02-08
"""
from alembic import op
import sqlalchemy as sa


revision = "024"
down_revision = "023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tenants",
        sa.Column("labor_rate", sa.Numeric(10, 2), nullable=False, server_default="100.00")
    )


def downgrade() -> None:
    op.drop_column("tenants", "labor_rate")
