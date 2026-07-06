"""add vehicles.active_warning_lights

Dashboard warning lights currently illuminated on a truck (comma-separated
labels), captured from the latest inspection.

Revision ID: 060
Revises: 059
Create Date: 2026-07-01
"""
from alembic import op
import sqlalchemy as sa


revision = "060"
down_revision = "059"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("vehicles", sa.Column("active_warning_lights", sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column("vehicles", "active_warning_lights")
