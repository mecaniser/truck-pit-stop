"""Add quote approval token and decline fields

Revision ID: 007
Revises: 006
Create Date: 2026-01-28
"""
from alembic import op
import sqlalchemy as sa


revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("quotes", sa.Column("is_declined", sa.Boolean(), nullable=False, server_default="false"))
    op.add_column("quotes", sa.Column("decline_notes", sa.Text(), nullable=True))
    op.add_column("quotes", sa.Column("approval_token", sa.String(64), nullable=True))
    op.create_index("ix_quotes_approval_token", "quotes", ["approval_token"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_quotes_approval_token", table_name="quotes")
    op.drop_column("quotes", "approval_token")
    op.drop_column("quotes", "decline_notes")
    op.drop_column("quotes", "is_declined")
