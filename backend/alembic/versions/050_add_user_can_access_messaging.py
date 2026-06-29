"""add users.can_access_messaging

Grants the Messages/Communications surface to roles that don't have it by
default (notably fleet managers). Server default false means existing fleet
managers become restricted; every other staff role keeps access by role.

Revision ID: 050
Revises: 049
Create Date: 2026-06-29
"""
from alembic import op
import sqlalchemy as sa


revision = "050"
down_revision = "049"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "can_access_messaging",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "can_access_messaging")
