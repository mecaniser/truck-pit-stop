"""merge fleet billing and invoice snapshot migration heads

Revision ID: 094_merge_fleet_invoice_heads
Revises: 093_fleet_billable_invoices, 092
"""


revision = "094_merge_fleet_invoice_heads"
down_revision = ("093_fleet_billable_invoices", "092")
branch_labels = None
depends_on = None


def upgrade() -> None:
    # This revision only joins two independently developed schema branches.
    pass


def downgrade() -> None:
    pass
