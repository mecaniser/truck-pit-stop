"""Add Zelle QR image field to tenants

Revision ID: 022
Revises: 021
Create Date: 2026-02-07
"""
from alembic import op
import sqlalchemy as sa


revision = "022"
down_revision = "021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tenants", sa.Column("zelle_qr_image", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("tenants", "zelle_qr_image")
