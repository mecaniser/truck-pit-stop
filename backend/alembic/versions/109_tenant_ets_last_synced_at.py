"""add tenants.ets_last_synced_at

Revision ID: 109_ets_last_synced_at
Revises: 108_conversion_export
Create Date: 2026-08-08

"""
from alembic import op
import sqlalchemy as sa

revision = "109_ets_last_synced_at"
down_revision = "108_conversion_export"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "tenants",
        sa.Column("ets_last_synced_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade():
    op.drop_column("tenants", "ets_last_synced_at")
