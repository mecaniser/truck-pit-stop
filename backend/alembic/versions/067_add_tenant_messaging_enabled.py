"""add messaging_enabled flag to tenants

Shop-wide switch for the customer Messages feature. Defaults to true so
existing shops keep messaging on; owners can turn it off (e.g. while the
feature is still being built) from Settings, which hides the Messages nav
and route and blocks the messages API.

Revision ID: 067
Revises: 066
Create Date: 2026-07-03
"""
from alembic import op
import sqlalchemy as sa


revision = "067"
down_revision = "066"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tenants",
        sa.Column(
            "messaging_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )


def downgrade() -> None:
    op.drop_column("tenants", "messaging_enabled")
