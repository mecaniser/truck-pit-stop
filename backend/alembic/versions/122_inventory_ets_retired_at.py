"""add inventory.ets_retired_at

A part that Easy Truck Shop no longer lists is not necessarily gone: it stays in
DieselBridge because repair orders reference it, and 97% of them sit at zero
stock. That made them qualify as "at or below reorder level", so three quarters
of the restock queue (516 of 686 rows in prod) was parts nobody will ever
reorder — a one-time item added in April to finish a job, still asking to be
restocked months later.

Record when a part stopped appearing in ETS so the restock predicate can skip
the ones that are both retired and empty, while a retired part that still has
stock on the shelf keeps counting as real inventory.

Set by the resync importer, not by hand: it is cleared again if the part
reappears in ETS.

Revision ID: 122_inventory_ets_retired_at
Revises: 121_inventory_canonical_sku
Create Date: 2026-08-23

"""
from alembic import op
import sqlalchemy as sa

revision = "122_inventory_ets_retired_at"
down_revision = "121_inventory_canonical_sku"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "inventory",
        sa.Column("ets_retired_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_inventory_ets_retired_at", "inventory", ["ets_retired_at"])


def downgrade():
    op.drop_index("ix_inventory_ets_retired_at", table_name="inventory")
    op.drop_column("inventory", "ets_retired_at")
