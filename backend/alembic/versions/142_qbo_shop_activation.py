"""Disabled shop admission and creation-only invoice enrollment."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "142_qbo_shop_activation"
# This guard branch was rebased after the receipt, exemption, customer-default,
# invoice-charge, and Fleet tender migrations landed. It must extend that sole
# production head rather than fork the historical hold revision.
down_revision = "146_fleet_payment_rail"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("quickbooks_shop_activations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("realm_id", sa.String(255), nullable=False),
        sa.Column("environment", sa.String(16), nullable=False),
        sa.Column("writer", sa.String(32), server_default="dieselbridge", nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("activated_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("tenant_id", name="uq_qbo_shop_activation_tenant"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_qbo_shop_activation_identity"),
        sa.CheckConstraint("environment IN ('sandbox','production')", name="ck_qbo_shop_environment"),
        sa.CheckConstraint("writer='dieselbridge' AND version>0", name="ck_qbo_shop_writer"),
        sa.CheckConstraint("NOT enabled OR activated_at IS NOT NULL", name="ck_qbo_shop_cutoff"),
        sa.CheckConstraint("deleted_at IS NULL", name="ck_qbo_shop_not_deleted"))
    op.add_column("invoices", sa.Column("qbo_shop_activation_id", postgresql.UUID(as_uuid=True)))
    op.create_index("ix_invoices_qbo_shop_activation_id", "invoices", ["qbo_shop_activation_id"])
    op.create_foreign_key("fk_invoice_qbo_shop_activation", "invoices", "quickbooks_shop_activations",
        ["tenant_id", "qbo_shop_activation_id"], ["tenant_id", "id"])
    op.execute("""CREATE FUNCTION protect_qbo_shop_activation() RETURNS trigger AS $$
    BEGIN
      IF TG_OP='DELETE' THEN RAISE EXCEPTION 'Managed shop classification cannot be removed'; END IF;
      IF TG_OP='INSERT' THEN
        IF NEW.enabled OR NEW.activated_at IS NOT NULL THEN RAISE EXCEPTION 'Create disabled management first'; END IF;
      ELSE
        IF (NEW.id,NEW.tenant_id,NEW.realm_id,NEW.environment,NEW.writer,NEW.version,NEW.created_at)
          IS DISTINCT FROM (OLD.id,OLD.tenant_id,OLD.realm_id,OLD.environment,OLD.writer,OLD.version,OLD.created_at)
          THEN RAISE EXCEPTION 'Activation identity is immutable'; END IF;
        IF NEW.activated_at IS DISTINCT FROM OLD.activated_at THEN RAISE EXCEPTION 'Cutoff is server owned'; END IF;
        IF NEW.enabled AND OLD.activated_at IS NULL THEN NEW.activated_at=clock_timestamp(); END IF;
      END IF;
      RETURN NEW;
    END; $$ LANGUAGE plpgsql""")
    op.execute("CREATE TRIGGER trg_qbo_shop_activation BEFORE INSERT OR UPDATE OR DELETE ON quickbooks_shop_activations FOR EACH ROW EXECUTE FUNCTION protect_qbo_shop_activation()")
    op.execute("""CREATE FUNCTION protect_qbo_invoice_enrollment() RETURNS trigger AS $$
    DECLARE a quickbooks_shop_activations%ROWTYPE;
    BEGIN
      IF TG_OP='UPDATE' AND NEW.qbo_shop_activation_id IS DISTINCT FROM OLD.qbo_shop_activation_id
        THEN RAISE EXCEPTION 'Enrollment is creation only and immutable'; END IF;
      IF TG_OP='INSERT' AND NEW.qbo_shop_activation_id IS NOT NULL THEN
        SELECT * INTO a FROM quickbooks_shop_activations WHERE id=NEW.qbo_shop_activation_id AND tenant_id=NEW.tenant_id FOR SHARE;
        IF NOT FOUND OR NOT a.enabled OR a.activated_at IS NULL OR NEW.created_at<=a.activated_at
          OR NEW.accounting_policy<>'standard' OR NEW.source IS NOT NULL OR NEW.supersedes_invoice_id IS NOT NULL
          THEN RAISE EXCEPTION 'Invoice not eligible for activation enrollment'; END IF;
      END IF;
      RETURN NEW;
    END; $$ LANGUAGE plpgsql""")
    op.execute("CREATE TRIGGER trg_qbo_invoice_enrollment BEFORE INSERT OR UPDATE ON invoices FOR EACH ROW EXECUTE FUNCTION protect_qbo_invoice_enrollment()")


def downgrade():
    if op.get_bind().execute(sa.text("SELECT 1 FROM quickbooks_shop_activations LIMIT 1")).first():
        raise RuntimeError("Managed-shop guards cannot be removed; disable admission instead")
    op.execute("DROP TRIGGER trg_qbo_invoice_enrollment ON invoices")
    op.execute("DROP FUNCTION protect_qbo_invoice_enrollment()")
    op.drop_constraint("fk_invoice_qbo_shop_activation", "invoices", type_="foreignkey")
    op.drop_index("ix_invoices_qbo_shop_activation_id", table_name="invoices")
    op.drop_column("invoices", "qbo_shop_activation_id")
    op.execute("DROP TRIGGER trg_qbo_shop_activation ON quickbooks_shop_activations")
    op.execute("DROP FUNCTION protect_qbo_shop_activation()")
    op.drop_table("quickbooks_shop_activations")
