"""add invoices.is_internal

Internal fleet work orders generate an internal invoice (cost record) on
completion — flagged so it's distinct from customer-facing invoices.

Revision ID: 051
Revises: 050
Create Date: 2026-06-30
"""
from alembic import op
import sqlalchemy as sa


revision = "051"
down_revision = "050"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "invoices",
        sa.Column("is_internal", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index("ix_invoices_is_internal", "invoices", ["is_internal"])


def downgrade() -> None:
    op.drop_index("ix_invoices_is_internal", table_name="invoices")
    op.drop_column("invoices", "is_internal")
