"""add 'missed' to inspectionstatus enum

A weekly inspection that never happens within the required 7-day window is
recorded as a MISSED inspection (a failed-compliance marker) by the weekly
fleet compliance task.

Revision ID: 055
Revises: 054
Create Date: 2026-07-01
"""
from alembic import op


revision = "055"
down_revision = "054"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ADD VALUE cannot run inside a transaction block on older Postgres.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE inspectionstatus ADD VALUE IF NOT EXISTS 'missed'")


def downgrade() -> None:
    # Postgres cannot drop a single enum value; leaving 'missed' in place is safe.
    pass
