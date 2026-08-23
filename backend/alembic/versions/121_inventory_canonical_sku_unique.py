"""prevent duplicate inventory rows for the same part number

The resync importer matched inventory on the raw "ETS-<number>" SKU string.
Easy Truck Shop part numbers are free text, so any drift in spelling forked a
second row instead of updating the first — "ETS-W261624" and "ETS-w261624" both
describing the one wiper motor on the shelf, with the location on one copy and
repair-order history split across both. 58 such groups had accumulated in prod.

Nothing in the schema prevented it. This adds the constraint that does: unique
on (tenant_id, canonical part number) for live rows, where the canonical form
drops the ETS- prefix and every non-alphanumeric and upper-cases the rest — the
same key the importer now matches on.

Partial on deleted_at IS NULL so the soft-deleted losers from the merge stay
recoverable, and so a part can be retired and re-added later.

Run backend/scripts/merge_duplicate_inventory.py first; this migration cannot
be applied while duplicates remain.

Revision ID: 121_inventory_canonical_sku
Revises: 120_merge_presentation_inventory
Create Date: 2026-08-23

"""
from alembic import op

revision = "121_inventory_canonical_sku"
down_revision = "120_merge_presentation_inventory"
branch_labels = None
depends_on = None

CANON = "upper(regexp_replace(regexp_replace(sku, '^ETS-', ''), '[^A-Za-z0-9]', '', 'g'))"


def upgrade():
    op.execute(
        f"""
        CREATE UNIQUE INDEX ux_inventory_tenant_canonical_sku
            ON inventory (tenant_id, {CANON})
         WHERE deleted_at IS NULL
        """
    )


def downgrade():
    op.execute("DROP INDEX IF EXISTS ux_inventory_tenant_canonical_sku")
