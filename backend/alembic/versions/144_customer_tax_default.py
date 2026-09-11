"""Customer tax default and immutable setting audit."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "144_customer_tax_default"
down_revision = "143_invoice_tax_exemption"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("customers", sa.Column("tax_exempt", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("customers", sa.Column("tax_exemption_support_reference", sa.String(255)))
    op.add_column("customers", sa.Column("tax_exemption_version", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("customers", sa.Column("tax_exemption_updated_at", sa.DateTime(timezone=True)))
    op.create_table("customer_tax_exemption_audits",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", sa.String(255), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("evidence", postgresql.JSONB(), nullable=False),
        sa.UniqueConstraint("tenant_id", "idempotency_key", name="uq_customer_tax_exemption_key"),
        sa.UniqueConstraint("customer_id", "version", name="uq_customer_tax_exemption_version"))
    op.create_index("ix_customer_tax_exemption_audits_tenant_id", "customer_tax_exemption_audits", ["tenant_id"])
    op.create_index("ix_customer_tax_exemption_audits_customer_id", "customer_tax_exemption_audits", ["customer_id"])
    op.execute("""CREATE FUNCTION protect_customer_tax_audit() RETURNS trigger LANGUAGE plpgsql AS $$
      BEGIN
        IF TG_OP = 'INSERT' THEN
          IF NOT EXISTS (SELECT 1 FROM customers WHERE id=NEW.customer_id
                         AND tenant_id=NEW.tenant_id AND deleted_at IS NULL) THEN
            RAISE EXCEPTION 'Customer tax audit tenant mismatch';
          END IF;
          RETURN NEW;
        END IF;
        RAISE EXCEPTION 'Customer tax default audit is immutable';
      END $$""")
    op.execute("""CREATE TRIGGER immutable_customer_tax_audit BEFORE INSERT OR UPDATE OR DELETE
      ON customer_tax_exemption_audits FOR EACH ROW EXECUTE FUNCTION protect_customer_tax_audit()""")


def downgrade():
    if op.get_bind().execute(sa.text("SELECT 1 FROM customer_tax_exemption_audits LIMIT 1")).first():
        raise RuntimeError("Customer tax default audits must be preserved")
    if op.get_bind().execute(sa.text("SELECT 1 FROM customers WHERE tax_exempt OR tax_exemption_version <> 0 LIMIT 1")).first():
        raise RuntimeError("Customer tax defaults must be preserved")
    op.drop_table("customer_tax_exemption_audits")
    op.execute("DROP FUNCTION protect_customer_tax_audit()")
    for column in ("tax_exemption_updated_at", "tax_exemption_version", "tax_exemption_support_reference", "tax_exempt"):
        op.drop_column("customers", column)
