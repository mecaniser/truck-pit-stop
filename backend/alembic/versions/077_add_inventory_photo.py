"""add inventory part photo

Revision ID: 077
Revises: 076
Create Date: 2026-07-18
"""
from alembic import op
import sqlalchemy as sa


revision = "077"
down_revision = "076"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("inventory", sa.Column("image_url", sa.String(length=500), nullable=True))
    op.add_column("inventory", sa.Column("cloudinary_public_id", sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column("inventory", "cloudinary_public_id")
    op.drop_column("inventory", "image_url")
