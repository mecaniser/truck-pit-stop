"""Explicit, immutable owner self-review audit; no evidence or grants seeded."""
from alembic import op
import sqlalchemy as sa

revision = "196_historical_owner_self_review"
down_revision = "195_historical_identity_proof"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("historical_invoice_evidence", sa.Column("verification_mode", sa.String(32), nullable=True))
    op.add_column("historical_invoice_decisions", sa.Column("evidence_verification_mode", sa.String(32), nullable=True))
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute("""
    CREATE OR REPLACE FUNCTION guard_historical_invoice_evidence_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE reviewer_role text; reviewer_tenant uuid; reviewer_active boolean; reviewer_deleted timestamptz;
    BEGIN
      IF TG_OP='DELETE' THEN RAISE EXCEPTION 'historical source evidence is immutable'; END IF;
      IF TG_OP='INSERT' THEN
        IF NEW.verified_at IS NOT NULL OR NEW.verification_mode IS NOT NULL
           OR NEW.verified_by_user_id IS NOT NULL OR NEW.verified_target_customer_id IS NOT NULL
           OR NEW.verified_target_legal_name IS NOT NULL OR NEW.verification_note IS NOT NULL
           OR NEW.identity_proof IS NOT NULL OR NEW.identity_proof_sha256 IS NOT NULL
        THEN RAISE EXCEPTION 'record source evidence before reviewing it'; END IF;
        RETURN NEW;
      END IF;
      IF OLD.verified_at IS NOT NULL THEN
        IF to_jsonb(OLD)-'updated_at' IS DISTINCT FROM to_jsonb(NEW)-'updated_at'
        THEN RAISE EXCEPTION 'verified historical evidence is immutable'; END IF;
      ELSIF (to_jsonb(OLD)-ARRAY['updated_at','verified_at','verified_by_user_id','verified_target_customer_id','verified_target_legal_name','verification_note','identity_proof','identity_proof_sha256','verification_mode'])
         IS DISTINCT FROM (to_jsonb(NEW)-ARRAY['updated_at','verified_at','verified_by_user_id','verified_target_customer_id','verified_target_legal_name','verification_note','identity_proof','identity_proof_sha256','verification_mode'])
      THEN RAISE EXCEPTION 'original historical source evidence is immutable';
      ELSIF NEW.verified_at IS NOT NULL THEN
        IF NEW.verified_by_user_id IS NULL OR NEW.verified_target_customer_id IS NULL
           OR NEW.verification_mode IS NULL OR NEW.verification_mode NOT IN ('independent','owner_self_review')
        THEN RAISE EXCEPTION 'explicit source verification audit is required'; END IF;
        SELECT role::text, tenant_id, is_active, deleted_at
          INTO reviewer_role, reviewer_tenant, reviewer_active, reviewer_deleted
          FROM users WHERE id=NEW.verified_by_user_id FOR SHARE;
        IF NOT FOUND OR reviewer_tenant IS DISTINCT FROM NEW.tenant_id
           OR reviewer_active IS DISTINCT FROM true OR reviewer_deleted IS NOT NULL
           OR reviewer_role IS NULL OR reviewer_role NOT IN ('garage_owner','garage_admin')
        THEN RAISE EXCEPTION 'active same-shop source reviewer required'; END IF;
        IF NEW.verification_mode='owner_self_review' THEN
          IF reviewer_role<>'garage_owner' OR NEW.verified_by_user_id<>NEW.recorded_by_user_id
          THEN RAISE EXCEPTION 'owner self-review requires the shop owner uploader'; END IF;
        ELSIF NEW.verified_by_user_id=NEW.recorded_by_user_id
        THEN RAISE EXCEPTION 'independent review requires a different staff member'; END IF;
      ELSIF NEW.verification_mode IS NOT NULL
      THEN RAISE EXCEPTION 'review mode requires completed verification'; END IF;
      IF (NEW.identity_proof IS NULL) IS DISTINCT FROM (NEW.identity_proof_sha256 IS NULL)
      THEN RAISE EXCEPTION 'identity proof and hash must be stored together'; END IF;
      RETURN NEW;
    END $$
    """)
    op.execute("DROP TRIGGER tr_historical_invoice_evidence_immutable ON historical_invoice_evidence")
    op.execute("CREATE TRIGGER tr_historical_invoice_evidence_immutable BEFORE INSERT OR UPDATE OR DELETE ON historical_invoice_evidence FOR EACH ROW EXECUTE FUNCTION guard_historical_invoice_evidence_immutable()")


def downgrade():
    # Losing the mode would erase whether an owner reviewed their own upload.
    if op.get_bind().dialect.name == "postgresql":
        op.execute("""DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM historical_invoice_evidence WHERE verification_mode IS NOT NULL)
             OR EXISTS (SELECT 1 FROM historical_invoice_decisions WHERE evidence_verification_mode IS NOT NULL)
          THEN RAISE EXCEPTION 'preserve verification mode audit; downgrade would erase review history'; END IF;
        END $$""")
        # Restore revision195 verbatim, including its original independent rule.
        op.execute("""
        CREATE OR REPLACE FUNCTION guard_historical_invoice_evidence_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
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
        op.execute("DROP TRIGGER tr_historical_invoice_evidence_immutable ON historical_invoice_evidence")
        op.execute("CREATE TRIGGER tr_historical_invoice_evidence_immutable BEFORE UPDATE OR DELETE ON historical_invoice_evidence FOR EACH ROW EXECUTE FUNCTION guard_historical_invoice_evidence_immutable()")
    else:
        # SQLite development migrations must also refuse silent audit loss.
        if op.get_bind().execute(sa.text("SELECT 1 FROM historical_invoice_evidence WHERE verification_mode IS NOT NULL UNION ALL SELECT 1 FROM historical_invoice_decisions WHERE evidence_verification_mode IS NOT NULL LIMIT 1")).first():
            raise RuntimeError("preserve verification mode audit before downgrade")
    op.drop_column("historical_invoice_decisions", "evidence_verification_mode")
    op.drop_column("historical_invoice_evidence", "verification_mode")
