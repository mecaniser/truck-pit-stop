"""Add quote sent_to_customer tracking

Revision ID: 008
Revises: 007
Create Date: 2026-01-29
"""
from alembic import op
import sqlalchemy as sa


revision = "008"
down_revision = "007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("quotes", sa.Column("sent_to_customer", sa.Boolean(), nullable=False, server_default="false"))
    op.add_column("quotes", sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("quotes", "sent_at")
    op.drop_column("quotes", "sent_to_customer")
