"""Retain one-time staff invoice tax-exemption audit."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "143_invoice_tax_exemption"
down_revision = "142_new_receipt_authorization"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("invoices", sa.Column("tax_exemption", postgresql.JSONB(), nullable=True))
    op.execute("""CREATE FUNCTION protect_invoice_tax_exemption() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF OLD.tax_exemption IS NOT NULL AND NEW.tax_exemption IS DISTINCT FROM OLD.tax_exemption THEN
        RAISE EXCEPTION 'Invoice tax exemption audit is immutable';
      END IF;
      RETURN NEW;
    END $$""")
    op.execute("""CREATE TRIGGER immutable_invoice_tax_exemption BEFORE UPDATE ON invoices
        FOR EACH ROW EXECUTE FUNCTION protect_invoice_tax_exemption()""")


def downgrade():
    if op.get_bind().execute(sa.text("SELECT 1 FROM invoices WHERE tax_exemption IS NOT NULL LIMIT 1")).first():
        raise RuntimeError("Invoice exemption audits must be preserved")
    op.execute("DROP TRIGGER immutable_invoice_tax_exemption ON invoices")
    op.execute("DROP FUNCTION protect_invoice_tax_exemption()")
    op.drop_column("invoices", "tax_exemption")
