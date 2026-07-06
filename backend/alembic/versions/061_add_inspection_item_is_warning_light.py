"""add fleet_inspection_items.is_warning_light

Marks a checklist item as a dashboard warning/telltale light (grouped inline
with the related physical checks) rather than a physical inspection point.

Revision ID: 061
Revises: 060
Create Date: 2026-07-01
"""
from alembic import op
import sqlalchemy as sa


revision = "061"
down_revision = "060"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "fleet_inspection_items",
        sa.Column("is_warning_light", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("fleet_inspection_items", "is_warning_light")
