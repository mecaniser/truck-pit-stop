"""Admit explicit historical export quarantine without changing existing rows."""
from alembic import op
import sqlalchemy as sa

revision = "141_historical_export_hold"
down_revision = "140_local_cash_policy"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_constraint("ck_invoice_accounting_policy", "invoices", type_="check")
    op.create_check_constraint("ck_invoice_accounting_policy", "invoices",
        "accounting_policy IN ('standard','local_cash_only','historical_export_hold')")


def downgrade():
    if op.get_bind().execute(sa.text("SELECT 1 FROM invoices WHERE accounting_policy='historical_export_hold' LIMIT 1")).first():
        raise RuntimeError("Individually resolve historical export holds before downgrade")
    op.drop_constraint("ck_invoice_accounting_policy", "invoices", type_="check")
    op.create_check_constraint("ck_invoice_accounting_policy", "invoices",
        "accounting_policy IN ('standard','local_cash_only')")
