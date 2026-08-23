"""add inventory.ets_imported_at

The resync importer decides whether a part has been hand-edited by comparing
updated_at against created_at. But the importer itself writes updated_at = now()
whenever it updates a row, so after the first update every later run sees its own
previous write as a human edit and skips the part forever.

Prod effect: 1081 of 1116 import-sourced parts (97%) were frozen. A clutch whose
stock was mis-entered as 984 and corrected to 1 in ETS on 07/31 still read 984 in
DieselBridge weeks later, because the row could never be updated again.

Record when the importer last wrote a row so "hand-edited" can mean "changed
since our last import" rather than "changed since creation". Backfilled to
updated_at for existing import-sourced rows: those were last written by an
import, so this unfreezes them without discarding genuine later edits — anything
a person changes from now on moves updated_at past ets_imported_at.

Revision ID: 123_inventory_ets_imported_at
Revises: 122_inventory_ets_retired_at
Create Date: 2026-08-23

"""
from alembic import op
import sqlalchemy as sa

revision = "123_inventory_ets_imported_at"
down_revision = "122_inventory_ets_retired_at"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "inventory",
        sa.Column("ets_imported_at", sa.DateTime(timezone=True), nullable=True),
    )
    # Existing import-sourced rows were last written by an import run, so treat
    # their current updated_at as that write. Rows a person has edited since will
    # be caught the moment they change again.
    op.execute(
        """
        UPDATE inventory SET ets_imported_at = updated_at
         WHERE source = 'easy_truck_shop_import' AND ets_imported_at IS NULL
        """
    )


def downgrade():
    op.drop_column("inventory", "ets_imported_at")
