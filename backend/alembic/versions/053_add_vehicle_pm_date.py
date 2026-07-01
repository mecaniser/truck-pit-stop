"""add vehicles.pm_due_date and pm_interval_days

Date-based preventive maintenance, complementing the existing mileage-based
PM. PM is due when either the odometer or the date threshold is reached.

Revision ID: 053
Revises: 052
Create Date: 2026-06-30
"""
from alembic import op
import sqlalchemy as sa


revision = "053"
down_revision = "052"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("vehicles", sa.Column("pm_interval_days", sa.Integer(), nullable=False, server_default="180"))
    op.add_column("vehicles", sa.Column("pm_due_date", sa.Date(), nullable=True))


def downgrade() -> None:
    op.drop_column("vehicles", "pm_due_date")
    op.drop_column("vehicles", "pm_interval_days")
