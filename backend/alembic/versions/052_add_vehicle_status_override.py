"""add vehicles.status_override

Manual truck status for the idle (no open work order) state, set by the
operator from the fleet board. NULL = auto.

Revision ID: 052
Revises: 051
Create Date: 2026-06-30
"""
from alembic import op
import sqlalchemy as sa


revision = "052"
down_revision = "051"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("vehicles", sa.Column("status_override", sa.String(length=20), nullable=True))


def downgrade() -> None:
    op.drop_column("vehicles", "status_override")
