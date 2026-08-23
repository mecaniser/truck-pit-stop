"""add inventory.is_placeholder and normalise "virtual" part names

Easy Truck Shop lets a tech add an ad-hoc "virtual" part to finish a repair
order for something that was never a catalog entry. The 2026-07-08 bulk import
swept 542 of those into inventory as if they were stock — 44% of the catalog,
every one attached to a repair order, none with stock, location, photo or price,
and all displaying the literal name "virtual" so they were indistinguishable
from each other in the parts list.

Flag them instead of deleting them (they are load-bearing for repair-order
history), and give them a readable name taken from the SKU, which is where
their real identity lives: ETS-Steer tire -> "Steer tire".

Revision ID: 120_inventory_is_placeholder
Revises: 119_ro_projection_cardinality
Create Date: 2026-08-23

"""
from alembic import op
import sqlalchemy as sa

revision = "120_inventory_is_placeholder"
down_revision = "119_ro_projection_cardinality"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "inventory",
        sa.Column("is_placeholder", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index("ix_inventory_is_placeholder", "inventory", ["is_placeholder"])

    # Mark existing ETS "virtual" rows, and replace the useless shared name with
    # the part number the SKU carries. Only rows that still look like untouched
    # placeholders are renamed, so a part someone already cleaned up by hand is
    # left exactly as they left it.
    op.execute(
        """
        UPDATE inventory
           SET is_placeholder = true,
               name = NULLIF(regexp_replace(sku, '^ETS-', ''), '')
         WHERE lower(trim(name)) = 'virtual'
           AND sku LIKE 'ETS-%'
        """
    )
    # Any straggler that had no usable SKU keeps a name rather than going blank.
    op.execute(
        """
        UPDATE inventory SET name = 'Placeholder part'
         WHERE is_placeholder = true AND (name IS NULL OR trim(name) = '')
        """
    )


def downgrade():
    # The original name was the literal "virtual" for every flagged row.
    op.execute("UPDATE inventory SET name = 'virtual' WHERE is_placeholder = true")
    op.drop_index("ix_inventory_is_placeholder", table_name="inventory")
    op.drop_column("inventory", "is_placeholder")
