"""Add explicit local-only invoice policy; preserve all historical defaults."""
from alembic import op
import sqlalchemy as sa

revision = "140_local_cash_policy"
down_revision = "139_qbo_gross_composition"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("invoices", sa.Column("accounting_policy", sa.String(32), nullable=False, server_default="standard"))
    op.add_column("invoices", sa.Column("cash_export_review_required", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_check_constraint("ck_invoice_accounting_policy", "invoices", "accounting_policy IN ('standard','local_cash_only')")
    op.drop_constraint("ck_invoice_payment_attempt_rail", "invoice_payment_attempts", type_="check")
    op.create_check_constraint("ck_invoice_payment_attempt_rail", "invoice_payment_attempts", "rail IN ('card','zelle','check','ach','cash')")
    if op.get_bind().dialect.name == "postgresql":
        # Keep the existing standard-rail function verbatim, inserting only a
        # narrowly validated local-cash branch. This preserves historical guards.
        definition = op.get_bind().execute(sa.text("SELECT pg_get_functiondef('enforce_db048_attempt_accounting_realm()'::regprocedure)")).scalar_one()
        cash_branch = """
              IF NEW.rail = 'cash' THEN
                IF NEW.source <> 'staff_cash' OR NEW.provider <> 'manual'
                   OR NEW.state <> 'confirmed' OR NEW.provider_configuration_version <> 0
                   OR NEW.provider_account_id IS NOT NULL OR NEW.provider_intent_id IS NOT NULL
                   OR NEW.provider_charge_id IS NOT NULL OR NEW.provider_event_id IS NOT NULL
                   OR NEW.card_fee_amount <> 0 OR NEW.card_fee_tax_amount <> 0
                   OR NEW.processor_fee_amount <> 0 OR NEW.unapplied_amount <> 0
                   OR NEW.received_amount <> NEW.principal_amount
                   OR NEW.applied_principal_amount <> NEW.principal_amount
                   OR NOT EXISTS (SELECT 1 FROM invoices i JOIN invoice_settlements s ON s.invoice_id=i.id
                     WHERE i.id=NEW.invoice_id AND i.tenant_id=NEW.tenant_id
                     AND s.id=NEW.settlement_id AND s.tenant_id=NEW.tenant_id
                     AND s.customer_id=NEW.customer_id AND i.accounting_policy='local_cash_only'
                     AND i.quickbooks_invoice_id IS NULL AND s.principal_total=NEW.principal_amount)
                THEN RAISE EXCEPTION 'DB-048 invalid local cash receipt'; END IF;
                RETURN NEW;
              END IF;
        """
        op.execute(sa.text(definition.replace("BEGIN", "BEGIN" + cash_branch, 1)))
        op.execute(sa.text("""
          CREATE FUNCTION guard_invoice_local_cash_policy() RETURNS trigger AS $$
          BEGIN
            IF OLD.accounting_policy='local_cash_only' AND (
               NEW.accounting_policy IS DISTINCT FROM OLD.accounting_policy
               OR NEW.quickbooks_invoice_id IS NOT NULL
               OR NEW.quickbooks_synced_at IS NOT NULL) THEN
              RAISE EXCEPTION 'Local cash accounting policy is immutable';
            END IF;
            RETURN NEW;
          END; $$ LANGUAGE plpgsql;
          CREATE TRIGGER trg_invoice_local_cash_policy BEFORE UPDATE ON invoices
          FOR EACH ROW EXECUTE FUNCTION guard_invoice_local_cash_policy();
        """))


def downgrade():
    # Never silently reinterpret or destroy real local receipts on rollback.
    if op.get_bind().execute(sa.text("SELECT 1 FROM invoices WHERE accounting_policy = 'local_cash_only' LIMIT 1")).first():
        raise RuntimeError("Local cash invoices exist; retain the additive schema on application rollback")
    if op.get_bind().dialect.name == "postgresql":
        op.execute(sa.text("DROP TRIGGER trg_invoice_local_cash_policy ON invoices; DROP FUNCTION guard_invoice_local_cash_policy()"))
        definition = op.get_bind().execute(sa.text("SELECT pg_get_functiondef('enforce_db048_attempt_accounting_realm()'::regprocedure)")).scalar_one()
        start = definition.index("IF NEW.rail = 'cash' THEN")
        end = definition.index("IF NOT EXISTS (", start)
        op.execute(sa.text(definition[:start] + definition[end:]))
    op.drop_constraint("ck_invoice_payment_attempt_rail", "invoice_payment_attempts", type_="check")
    op.create_check_constraint("ck_invoice_payment_attempt_rail", "invoice_payment_attempts", "rail IN ('card','zelle','check','ach')")
    op.drop_constraint("ck_invoice_accounting_policy", "invoices", type_="check")
    op.drop_column("invoices", "accounting_policy")
    op.drop_column("invoices", "cash_export_review_required")
