"""Add declined status to repair order enum

Revision ID: 016
Revises: 015
Create Date: 2026-02-06

"""
from alembic import op

revision = '016'
down_revision = '015'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add 'declined' value to the repairorderstatus enum
    op.execute("ALTER TYPE repairorderstatus ADD VALUE IF NOT EXISTS 'declined' AFTER 'quoted'")


def downgrade() -> None:
    # PostgreSQL doesn't support removing enum values easily
    # Would need to recreate the type, which is complex
    pass
