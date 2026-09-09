"""Persist the customer surcharge journal identity separately from deposits."""
from alembic import op
import sqlalchemy as sa

revision = "138_payment_fee_journal_identity"
down_revision = "137_merge_fleet_invoice_payments"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("payment_accounting_links", sa.Column("provider_fee_journal_id", sa.String(255), nullable=True))


def downgrade():
    connection = op.get_bind()
    if connection.execute(sa.text("SELECT 1 FROM payment_accounting_links WHERE provider_fee_journal_id IS NOT NULL LIMIT 1")).first():
        raise RuntimeError("Cannot remove persisted customer fee journal identities")
    op.drop_column("payment_accounting_links", "provider_fee_journal_id")
