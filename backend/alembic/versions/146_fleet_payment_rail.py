"""Restore canonical staff-verified Fleet instruments without historical backfill."""
from alembic import op
import sqlalchemy as sa

revision = "146_fleet_payment_rail"
down_revision = "145_invoice_charge_adjustments"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_constraint("ck_invoice_payment_attempt_rail", "invoice_payment_attempts", type_="check")
    op.create_check_constraint("ck_invoice_payment_attempt_rail", "invoice_payment_attempts",
                               "rail IN ('card','zelle','check','ach','fleet_payment','cash')")
    op.create_check_constraint("ck_invoice_payment_fleet_money", "invoice_payment_attempts",
        "rail <> 'fleet_payment' OR (provider = 'manual' AND card_fee_amount = 0 AND card_fee_tax_amount = 0 AND processor_fee_amount = 0)")
    op.create_index("uq_invoice_payment_fleet_reference", "invoice_payment_attempts",
                    ["tenant_id", "manual_reference_fingerprint"], unique=True,
                    postgresql_where=sa.text("rail = 'fleet_payment' AND manual_reference_fingerprint IS NOT NULL"))
    op.execute("""CREATE FUNCTION guard_db048_fleet_evidence() RETURNS trigger LANGUAGE plpgsql AS $$
      BEGIN
        IF TG_OP = 'UPDATE' AND OLD.rail = 'fleet_payment'
          AND NEW.manual_evidence IS DISTINCT FROM OLD.manual_evidence THEN
          RAISE EXCEPTION 'Fleet instrument evidence is immutable';
        END IF;
        IF NEW.rail = 'fleet_payment' AND (
          jsonb_typeof(NEW.manual_evidence::jsonb) IS DISTINCT FROM 'object'
          OR COALESCE(NEW.manual_evidence->>'fleet_provider', '') NOT IN ('EFS','Comchek','T-Chek','Other')
          OR length(trim(COALESCE(NEW.manual_evidence->>'reference_number', ''))) NOT BETWEEN 1 AND 255
          OR (NEW.manual_evidence->>'fleet_provider' = 'Other' AND
              length(trim(COALESCE(NEW.manual_evidence->>'fleet_provider_name', ''))) NOT BETWEEN 1 AND 100)
        ) THEN RAISE EXCEPTION 'Fleet provider and instrument reference are required'; END IF;
        RETURN NEW;
      END $$""")
    op.execute("""CREATE TRIGGER trg_db048_fleet_evidence BEFORE INSERT OR UPDATE
      ON invoice_payment_attempts FOR EACH ROW EXECUTE FUNCTION guard_db048_fleet_evidence()""")


def downgrade():
    if op.get_bind().execute(sa.text("SELECT 1 FROM invoice_payment_attempts WHERE rail='fleet_payment' LIMIT 1")).first():
        raise RuntimeError("Fleet payment attempts and their audit must be preserved")
    op.execute("DROP TRIGGER trg_db048_fleet_evidence ON invoice_payment_attempts")
    op.execute("DROP FUNCTION guard_db048_fleet_evidence()")
    op.drop_index("uq_invoice_payment_fleet_reference", table_name="invoice_payment_attempts")
    op.drop_constraint("ck_invoice_payment_fleet_money", "invoice_payment_attempts", type_="check")
    op.drop_constraint("ck_invoice_payment_attempt_rail", "invoice_payment_attempts", type_="check")
    op.create_check_constraint("ck_invoice_payment_attempt_rail", "invoice_payment_attempts", "rail IN ('card','zelle','check','ach','cash')")
