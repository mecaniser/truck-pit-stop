"""add landing partner profile fields to tenants

Revision ID: 044
Revises: 043
Create Date: 2026-04-11
"""
from alembic import op
import sqlalchemy as sa


revision = "044"
down_revision = "043"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tenants", sa.Column("partner_summary", sa.String(length=280), nullable=True))
    op.add_column("tenants", sa.Column("partner_services", sa.String(length=180), nullable=True))


def downgrade() -> None:
    op.drop_column("tenants", "partner_services")
    op.drop_column("tenants", "partner_summary")
