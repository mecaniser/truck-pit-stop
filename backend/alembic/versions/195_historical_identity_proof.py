"""Reviewed correspondence identity proof; no evidence, mappings or grants seeded."""
from alembic import op
import sqlalchemy as sa

revision = "195_historical_identity_proof"
down_revision = "194_invoice_review_url"
branch_labels = None
depends_on = None


def _customer_guard(proof_email):
    email_clause = """
          IF lower(btrim(OLD.email)) IS DISTINCT FROM lower(btrim(NEW.email)) AND EXISTS (
            SELECT 1 FROM historical_invoice_mappings m
            JOIN historical_invoice_evidence e ON e.id=m.evidence_id AND e.tenant_id=m.tenant_id
            WHERE m.tenant_id=OLD.tenant_id AND m.target_customer_id=OLD.id AND e.identity_proof IS NOT NULL
          ) THEN RAISE EXCEPTION 'revoke reviewed correspondence mappings before changing bill-to email'; END IF;
    """ if proof_email else ""
    op.execute(f"""
    CREATE OR REPLACE FUNCTION guard_historical_invoice_customer_identity() RETURNS trigger
    LANGUAGE plpgsql AS $$ BEGIN
      IF TG_OP='DELETE' THEN
        IF EXISTS (SELECT 1 FROM historical_invoice_mappings m WHERE m.tenant_id=OLD.tenant_id AND m.target_customer_id=OLD.id)
        THEN RAISE EXCEPTION 'revoke reviewed historical invoice mappings before deleting bill-to'; END IF;
        RETURN OLD;
      END IF;
      IF (OLD.first_name IS DISTINCT FROM NEW.first_name OR OLD.last_name IS DISTINCT FROM NEW.last_name OR OLD.company_name IS DISTINCT FROM NEW.company_name)
         AND EXISTS (SELECT 1 FROM historical_invoice_mappings m WHERE m.tenant_id=OLD.tenant_id AND m.target_customer_id=OLD.id)
      THEN RAISE EXCEPTION 'revoke reviewed historical invoice mappings before changing bill-to identity'; END IF;
      {email_clause}
      RETURN NEW;
    END $$
    """)
    op.execute("DROP TRIGGER tr_guard_historical_invoice_customer_identity ON customers")
    fields = "first_name,last_name,company_name,email" if proof_email else "first_name,last_name,company_name"
    op.execute(f"CREATE TRIGGER tr_guard_historical_invoice_customer_identity BEFORE UPDATE OF {fields} OR DELETE ON customers FOR EACH ROW EXECUTE FUNCTION guard_historical_invoice_customer_identity()")


def upgrade():
    op.add_column("historical_invoice_evidence", sa.Column("identity_proof", sa.Text(), nullable=True))
    op.add_column("historical_invoice_evidence", sa.Column("identity_proof_sha256", sa.String(64), nullable=True))
    op.add_column("historical_invoice_decisions", sa.Column("evidence_identity_proof_sha256", sa.String(64), nullable=True))
    if op.get_bind().dialect.name != "postgresql":
        return
    _customer_guard(True)
    op.execute("""
    CREATE FUNCTION lock_historical_customer_identity() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE scope uuid;
    BEGIN
      scope := CASE WHEN TG_OP='DELETE' THEN OLD.tenant_id ELSE NEW.tenant_id END;
      IF TG_OP='UPDATE' AND OLD.tenant_id IS DISTINCT FROM NEW.tenant_id THEN
        PERFORM pg_advisory_xact_lock(hashtextextended(LEAST(OLD.tenant_id::text, NEW.tenant_id::text), 94094));
        PERFORM pg_advisory_xact_lock(hashtextextended(GREATEST(OLD.tenant_id::text, NEW.tenant_id::text), 94094));
      ELSE
        PERFORM pg_advisory_xact_lock(hashtextextended(scope::text, 94094));
      END IF;
      IF TG_OP='DELETE' THEN RETURN OLD; END IF;
      IF TG_OP='UPDATE' AND (OLD.tenant_id IS DISTINCT FROM NEW.tenant_id OR NEW.deleted_at IS NOT NULL)
        AND EXISTS (SELECT 1 FROM historical_invoice_mappings m JOIN historical_invoice_evidence e
          ON e.id=m.evidence_id AND e.tenant_id=m.tenant_id WHERE m.tenant_id=OLD.tenant_id
          AND m.target_customer_id=OLD.id AND e.identity_proof IS NOT NULL)
      THEN RAISE EXCEPTION 'revoke reviewed correspondence mappings before moving or archiving bill-to'; END IF;
      RETURN NEW;
    END $$
    """)
    # PostgreSQL executes same-kind triggers alphabetically: serialize before guards read mappings.
    op.execute("CREATE TRIGGER tr_00_historical_customer_identity_lock BEFORE INSERT OR UPDATE OF email,deleted_at,tenant_id OR DELETE ON customers FOR EACH ROW EXECUTE FUNCTION lock_historical_customer_identity()")
    op.execute("""
    CREATE FUNCTION guard_historical_invoice_evidence_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF TG_OP='DELETE' THEN RAISE EXCEPTION 'historical source evidence is immutable'; END IF;
      IF OLD.verified_at IS NOT NULL THEN
        IF to_jsonb(OLD)-'updated_at' IS DISTINCT FROM to_jsonb(NEW)-'updated_at'
        THEN RAISE EXCEPTION 'verified historical evidence is immutable'; END IF;
      ELSIF (to_jsonb(OLD)-ARRAY['updated_at','verified_at','verified_by_user_id','verified_target_customer_id','verified_target_legal_name','verification_note','identity_proof','identity_proof_sha256'])
         IS DISTINCT FROM (to_jsonb(NEW)-ARRAY['updated_at','verified_at','verified_by_user_id','verified_target_customer_id','verified_target_legal_name','verification_note','identity_proof','identity_proof_sha256'])
      THEN RAISE EXCEPTION 'original historical source evidence is immutable';
      ELSIF NEW.verified_at IS NOT NULL AND (NEW.verified_by_user_id IS NULL OR NEW.verified_by_user_id=NEW.recorded_by_user_id OR NEW.verified_target_customer_id IS NULL)
      THEN RAISE EXCEPTION 'independent source verification is required'; END IF;
      IF (NEW.identity_proof IS NULL) IS DISTINCT FROM (NEW.identity_proof_sha256 IS NULL)
      THEN RAISE EXCEPTION 'identity proof and hash must be stored together'; END IF;
      RETURN NEW;
    END $$
    """)
    op.execute("CREATE TRIGGER tr_historical_invoice_evidence_immutable BEFORE UPDATE OR DELETE ON historical_invoice_evidence FOR EACH ROW EXECUTE FUNCTION guard_historical_invoice_evidence_immutable()")
    op.execute("CREATE FUNCTION guard_historical_invoice_decision_immutable() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'historical invoice decisions are append-only'; END $$")
    op.execute("CREATE TRIGGER tr_historical_invoice_decision_immutable BEFORE UPDATE OR DELETE ON historical_invoice_decisions FOR EACH ROW EXECUTE FUNCTION guard_historical_invoice_decision_immutable()")


def downgrade():
    if op.get_bind().dialect.name == "postgresql":
        op.execute("""DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM historical_invoice_evidence WHERE identity_proof IS NOT NULL)
             OR EXISTS (SELECT 1 FROM historical_invoice_decisions WHERE evidence_identity_proof_sha256 IS NOT NULL)
          THEN RAISE EXCEPTION 'preserve reviewed identity proofs; downgrade would erase audit evidence'; END IF;
        END $$""")
        op.execute("DROP TRIGGER tr_historical_invoice_decision_immutable ON historical_invoice_decisions")
        op.execute("DROP FUNCTION guard_historical_invoice_decision_immutable()")
        op.execute("DROP TRIGGER tr_historical_invoice_evidence_immutable ON historical_invoice_evidence")
        op.execute("DROP FUNCTION guard_historical_invoice_evidence_immutable()")
        op.execute("DROP TRIGGER tr_00_historical_customer_identity_lock ON customers")
        op.execute("DROP FUNCTION lock_historical_customer_identity()")
        _customer_guard(False)
    op.drop_column("historical_invoice_decisions", "evidence_identity_proof_sha256")
    op.drop_column("historical_invoice_evidence", "identity_proof_sha256")
    op.drop_column("historical_invoice_evidence", "identity_proof")
