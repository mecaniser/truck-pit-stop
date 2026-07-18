"""add ets_external_id to customers and vehicles for Easy Truck Shop resync

The original Easy Truck Shop import stored no stable reference back to the
source record (customers/vehicles got fresh UUIDs), so a re-scrape had no way
to tell an already-imported row from a new one. This adds a nullable, indexed
ets_external_id holding the Easy Truck Shop numeric record id, letting the
resync tool match scraped records to existing rows exactly and idempotently.

Repair orders already carry a deterministic order_number
(ETS-{service_no}-{customer_id}) and need no new column.

Revision ID: 080
Revises: 079
Create Date: 2026-07-18
"""
from alembic import op
import sqlalchemy as sa


revision = "080"
down_revision = "079"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table in ("customers", "vehicles"):
        op.add_column(table, sa.Column("ets_external_id", sa.String(length=50), nullable=True))
        op.create_index(f"ix_{table}_ets_external_id", table, ["ets_external_id"])


def downgrade() -> None:
    for table in ("customers", "vehicles"):
        op.drop_index(f"ix_{table}_ets_external_id", table_name=table)
        op.drop_column(table, "ets_external_id")
