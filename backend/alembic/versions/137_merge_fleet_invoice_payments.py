"""Join Fleet and DB-048 without rewriting applied migration identities.

Revision ID: 137_merge_fleet_invoice_payments
Revises: 135_fleet_board_opened_at, 136_invoice_payment_projection

Both branches descend from 134_fleet_membership_ended_by. Alembic applies
whichever branch is absent before reaching this no-op merge, preserving both
production Fleet databases and populated DB-048 sandbox databases.
"""

revision = "137_merge_fleet_invoice_payments"
down_revision = ("135_fleet_board_opened_at", "136_invoice_payment_projection")
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
