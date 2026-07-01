"""lower default pm_interval_days from 180 to 70 (~10 weeks)

Half-a-year PM cadence was too long a preset. Typical PM is every ~10 weeks
to a few months, so the default is now 70 days. Trucks still sitting on the
old default (180) are treated as never-customized and moved to the new default;
any truck with a deliberately different interval is left untouched.

Revision ID: 054
Revises: 053
Create Date: 2026-07-01
"""
from alembic import op
import sqlalchemy as sa


revision = "054"
down_revision = "053"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("vehicles", "pm_interval_days", server_default="70")
    op.execute("UPDATE vehicles SET pm_interval_days = 70 WHERE pm_interval_days = 180")


def downgrade() -> None:
    op.alter_column("vehicles", "pm_interval_days", server_default="180")
    op.execute("UPDATE vehicles SET pm_interval_days = 180 WHERE pm_interval_days = 70")
