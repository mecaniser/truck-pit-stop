"""Append-only reversible invoice charge audit."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "145_invoice_charge_adjustments"
down_revision = "144_customer_tax_default"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("invoice_charge_adjustments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("invoice_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("invoices.id"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", sa.String(255), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("evidence", postgresql.JSONB(), nullable=False),
        sa.UniqueConstraint("invoice_id", "idempotency_key", name="uq_invoice_charge_adjustment_key"),
        sa.UniqueConstraint("invoice_id", "version", name="uq_invoice_charge_adjustment_version"))
    op.create_index("ix_invoice_charge_adjustments_tenant_id", "invoice_charge_adjustments", ["tenant_id"])
    op.create_index("ix_invoice_charge_adjustments_invoice_id", "invoice_charge_adjustments", ["invoice_id"])
    op.execute("""CREATE FUNCTION protect_invoice_charge_adjustment() RETURNS trigger LANGUAGE plpgsql AS $$
      BEGIN
        IF TG_OP = 'INSERT' THEN
          IF NOT EXISTS (SELECT 1 FROM invoices WHERE id=NEW.invoice_id AND tenant_id=NEW.tenant_id) THEN
            RAISE EXCEPTION 'Invoice charge adjustment tenant mismatch';
          END IF;
          RETURN NEW;
        END IF;
        RAISE EXCEPTION 'Invoice charge adjustment audit is immutable';
      END $$""")
    op.execute("""CREATE TRIGGER immutable_invoice_charge_adjustment BEFORE INSERT OR UPDATE OR DELETE
      ON invoice_charge_adjustments FOR EACH ROW EXECUTE FUNCTION protect_invoice_charge_adjustment()""")


def downgrade():
    if op.get_bind().execute(sa.text("SELECT 1 FROM invoice_charge_adjustments LIMIT 1")).first():
        raise RuntimeError("Invoice charge adjustment audits must be preserved")
    op.drop_table("invoice_charge_adjustments")
    op.execute("DROP FUNCTION protect_invoice_charge_adjustment()")
