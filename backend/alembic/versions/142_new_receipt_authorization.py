"""Authorize only genuinely new receipt accounting; existing attempts stay null."""
from alembic import op
import sqlalchemy as sa

revision = "142_new_receipt_authorization"
down_revision = "141_historical_export_hold"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("invoice_payment_attempts", sa.Column("new_receipt_accounting_authorization", sa.JSON(none_as_null=True), nullable=True))
    op.execute("""CREATE FUNCTION protect_new_receipt_authorization() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF NEW.new_receipt_accounting_authorization::jsonb IS DISTINCT FROM OLD.new_receipt_accounting_authorization::jsonb THEN
        RAISE EXCEPTION 'New receipt accounting authorization is immutable';
      END IF;
      RETURN NEW;
    END $$""")
    op.execute("""CREATE TRIGGER immutable_new_receipt_authorization BEFORE UPDATE ON invoice_payment_attempts
        FOR EACH ROW EXECUTE FUNCTION protect_new_receipt_authorization()""")


def downgrade():
    if op.get_bind().execute(sa.text("SELECT 1 FROM invoice_payment_attempts WHERE new_receipt_accounting_authorization IS NOT NULL LIMIT 1")).first():
        raise RuntimeError("New receipt authorizations must be preserved; downgrade is unavailable")
    op.execute("DROP TRIGGER immutable_new_receipt_authorization ON invoice_payment_attempts")
    op.execute("DROP FUNCTION protect_new_receipt_authorization()")
    op.drop_column("invoice_payment_attempts", "new_receipt_accounting_authorization")
