"""add invoices.ets_invoiced_at

DieselBridge's "Invoiced Hours" report grouped repair orders by PAYMENT date
(the same cash basis used for revenue), while Easy Truck Shop's own Invoiced
Hours chart groups by the date the invoice was issued — verified by summing
each August invoice's true labor hours (a field reverse-engineered from ETS's
page JSON, see lib/invoice_json.js) grouped by invoice date: 683.10h against
ETS's reported 683.2h, a 0.01% difference. Grouped by payment date instead, the
same underlying data gives 943.90h — 38% too high, because some July work paid
in August pulls in, and some August work not yet paid drops out.

Nothing on the Invoice row currently holds ETS's real invoice date:
created_at is stamped at import time, not the date shown on the ETS invoice.
Record it separately so the Invoiced Hours query can group by it while every
other report (revenue, parts, labor $) keeps its existing, deliberate cash
basis unchanged.

Revision ID: 125_invoice_ets_invoiced_at
Revises: 124_parts_operations_v1
Create Date: 2026-08-24

"""
from alembic import op
import sqlalchemy as sa

revision = "125_invoice_ets_invoiced_at"
down_revision = "124_parts_operations_v1"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "invoices",
        sa.Column("ets_invoiced_at", sa.Date(), nullable=True),
    )
    op.create_index("ix_invoices_ets_invoiced_at", "invoices", ["ets_invoiced_at"])


def downgrade():
    op.drop_index("ix_invoices_ets_invoiced_at", table_name="invoices")
    op.drop_column("invoices", "ets_invoiced_at")
