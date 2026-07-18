"""add inventory warehouse location

Revision ID: 078
Revises: 077
Create Date: 2026-07-18
"""
from alembic import op
import sqlalchemy as sa


revision = "078"
down_revision = "077"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("inventory", sa.Column("location", sa.String(length=100), nullable=True))


def downgrade() -> None:
    op.drop_column("inventory", "location")
