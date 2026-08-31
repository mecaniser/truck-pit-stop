"""Give the shop a plain-text note on the repair order.

`internal_notes` looks like the place for one, but it is not a note field: it
carries a JSON envelope that pricing, quoting, invoicing, mechanic time
tracking, the fleet endpoints, the dashboard and the customer portal all parse.
`get_selected_services_total` reads `selected_services` out of it to price the
invoice, so prose written there does not merely fail to display — it makes the
services unparseable and the order's labour total silently collapses to zero.

So the shop's note gets its own column. `customer_notes` already exists and is
genuinely free text, and keeps carrying the note the customer is meant to read.

Revision ID: 130_repair_order_shop_notes
Revises: 129_repair_order_mileage_carried
"""
from alembic import op
import sqlalchemy as sa

revision = "130_repair_order_shop_notes"
down_revision = "129_repair_order_mileage_carried"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("repair_orders", sa.Column("shop_notes", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("repair_orders", "shop_notes")
