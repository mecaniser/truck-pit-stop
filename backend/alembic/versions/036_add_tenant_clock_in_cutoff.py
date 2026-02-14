"""add tenant minimum clock-in remaining minutes

Revision ID: 036
Revises: 035
"""
from alembic import op
import sqlalchemy as sa

revision = "036"
down_revision = "035"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tenants",
        sa.Column("minimum_clock_in_remaining_minutes", sa.Integer(), nullable=False, server_default="60"),
    )


def downgrade() -> None:
    op.drop_column("tenants", "minimum_clock_in_remaining_minutes")
