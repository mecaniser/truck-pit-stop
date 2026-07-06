"""add service_categories.is_pm

Flags a service category as preventive maintenance. Services in a PM category
are the jobs offered when scoping a fleet PM work order — replacing the previous
match on the literal category name "PM Services", so the category can be renamed
without breaking the fleet PM picker.

Backfills is_pm=True for any existing category named "PM Services".

Revision ID: 058
Revises: 057
Create Date: 2026-07-05
"""
from alembic import op
import sqlalchemy as sa


revision = "058"
down_revision = "057"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "service_categories",
        sa.Column("is_pm", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    # Backfill: existing "PM Services" categories keep driving the PM picker.
    op.execute(
        "UPDATE service_categories SET is_pm = true WHERE lower(name) = 'pm services'"
    )


def downgrade() -> None:
    op.drop_column("service_categories", "is_pm")
