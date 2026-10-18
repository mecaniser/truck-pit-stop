"""DB-135 immutable, B1-only historical receivable evidence; no backfill."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "179_db135_receivables"
down_revision = "178_merge_maintenance_bindings"
branch_labels = None
depends_on = None

UUID = postgresql.UUID(as_uuid=True)


def upgrade():
    op.create_table(
        "invoice_receivable_attestation_runs",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("tenant_id", UUID, sa.ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("manifest_digest", sa.String(64), nullable=False),
        sa.Column("invoice_ids", postgresql.JSONB(), nullable=False),
        sa.Column("approved_entries", postgresql.JSONB(), nullable=False),
        sa.Column("fingerprint_version", sa.String(32), nullable=False),
        sa.Column("expected_insert_count", sa.Integer(), nullable=False),
        sa.Column("authorization_reference", sa.String(255), nullable=False),
        sa.Column("reviewer_user_id", UUID, sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("executor_user_id", UUID, sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("tenant_id", "id", name="uq_db135_run_tenant_id"),
        sa.UniqueConstraint("tenant_id", "manifest_digest", name="uq_db135_run_manifest"),
        sa.CheckConstraint("state = 'applied'", name="ck_db135_run_applied"),
        sa.CheckConstraint("reviewer_user_id <> executor_user_id", name="ck_db135_run_independent"),
        sa.CheckConstraint("expected_insert_count > 0", name="ck_db135_run_nonempty"),
        sa.CheckConstraint("manifest_digest ~ '^[0-9a-f]{64}$'", name="ck_db135_run_digest"),
        sa.CheckConstraint("jsonb_typeof(invoice_ids) = 'array' AND jsonb_typeof(approved_entries) = 'object'", name="ck_db135_run_manifest_shape"),
    )
    op.create_table(
        "invoice_receivable_attestations",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("tenant_id", UUID, nullable=False),
        sa.Column("invoice_id", UUID, sa.ForeignKey("invoices.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("repair_order_id", UUID, nullable=False),
        sa.Column("customer_id", UUID, nullable=False),
        sa.Column("run_id", UUID, nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("supersedes_id", UUID),
        sa.Column("decision", sa.String(32), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("principal_total_cents", sa.BigInteger(), nullable=False),
        sa.Column("confirmed_principal_cents", sa.BigInteger(), nullable=False),
        sa.Column("source_fingerprint", sa.String(64), nullable=False),
        sa.Column("fingerprint_version", sa.String(32), nullable=False),
        sa.Column("evidence_digest", sa.String(64), nullable=False),
        sa.Column("manifest_digest", sa.String(64), nullable=False),
        sa.Column("reviewer_user_id", UUID, sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("executor_user_id", UUID, sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=False),
        sa.Column("audit_reference", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("tenant_id", "id", name="uq_db135_attestation_tenant_id"),
        sa.UniqueConstraint("tenant_id", "invoice_id", "version", name="uq_db135_invoice_version"),
        sa.UniqueConstraint("tenant_id", "run_id", "invoice_id", name="uq_db135_run_invoice"),
        sa.UniqueConstraint("supersedes_id", name="uq_db135_single_successor"),
        sa.ForeignKeyConstraint(["tenant_id", "repair_order_id"], ["repair_orders.tenant_id", "repair_orders.id"], ondelete="RESTRICT", name="fk_db135_attestation_order"),
        sa.ForeignKeyConstraint(["tenant_id", "customer_id"], ["customers.tenant_id", "customers.id"], ondelete="RESTRICT", name="fk_db135_attestation_customer"),
        sa.ForeignKeyConstraint(["tenant_id", "run_id"], ["invoice_receivable_attestation_runs.tenant_id", "invoice_receivable_attestation_runs.id"], ondelete="RESTRICT", name="fk_db135_attestation_run"),
        sa.ForeignKeyConstraint(["tenant_id", "supersedes_id"], ["invoice_receivable_attestations.tenant_id", "invoice_receivable_attestations.id"], ondelete="RESTRICT", name="fk_db135_attestation_predecessor"),
        sa.CheckConstraint("version >= 1", name="ck_db135_attestation_version"),
        sa.CheckConstraint("(version = 1 AND supersedes_id IS NULL) OR (version > 1 AND supersedes_id IS NOT NULL)", name="ck_db135_attestation_predecessor"),
        sa.CheckConstraint("decision IN ('verified_open', 'verified_paid_tender')", name="ck_db135_attestation_decision"),
        sa.CheckConstraint("currency = 'USD'", name="ck_db135_attestation_currency"),
        sa.CheckConstraint("principal_total_cents > 0 AND confirmed_principal_cents >= 0 AND confirmed_principal_cents <= principal_total_cents", name="ck_db135_attestation_amounts"),
        sa.CheckConstraint("decision <> 'verified_open' OR confirmed_principal_cents = 0", name="ck_db135_attestation_open"),
        sa.CheckConstraint("reviewer_user_id <> executor_user_id", name="ck_db135_attestation_independent"),
        sa.CheckConstraint("applied_at >= reviewed_at AND valid_until > applied_at AND valid_until <= reviewed_at + interval '7 days'", name="ck_db135_attestation_validity"),
        sa.CheckConstraint("source_fingerprint ~ '^[0-9a-f]{64}$' AND evidence_digest ~ '^[0-9a-f]{64}$' AND manifest_digest ~ '^[0-9a-f]{64}$'", name="ck_db135_attestation_digests"),
    )
    op.create_index("ix_db135_attestation_lookup", "invoice_receivable_attestations", ["tenant_id", "invoice_id", "version"])
    op.execute("""CREATE FUNCTION db135_guard_run() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE reviewer users%ROWTYPE; executor users%ROWTYPE;
    BEGIN
      IF TG_OP <> 'INSERT' THEN RAISE EXCEPTION 'DB135 run evidence is immutable'; END IF;
      SELECT * INTO reviewer FROM users WHERE id = NEW.reviewer_user_id;
      SELECT * INTO executor FROM users WHERE id = NEW.executor_user_id;
      IF reviewer.tenant_id IS DISTINCT FROM NEW.tenant_id OR executor.tenant_id IS DISTINCT FROM NEW.tenant_id
         OR reviewer.is_active IS NOT TRUE OR executor.is_active IS NOT TRUE
         OR reviewer.deleted_at IS NOT NULL OR executor.deleted_at IS NOT NULL
         OR (reviewer.role::text <> 'garage_owner' AND
             (reviewer.role::text <> 'garage_admin' OR reviewer.permissions->>'payments' IS DISTINCT FROM 'true'))
         OR (executor.role::text <> 'garage_owner' AND
             (executor.role::text <> 'garage_admin' OR executor.permissions->>'payments' IS DISTINCT FROM 'true')) THEN
        RAISE EXCEPTION 'DB135 reviewer/executor tenant or role mismatch';
      END IF;
      IF jsonb_array_length(NEW.invoice_ids) <> NEW.expected_insert_count
         OR (SELECT count(*) FROM jsonb_object_keys(NEW.approved_entries)) <> NEW.expected_insert_count THEN
        RAISE EXCEPTION 'DB135 run manifest count mismatch';
      END IF;
      RETURN NEW;
    END $$""")
    op.execute("CREATE TRIGGER trg_db135_run_guard BEFORE INSERT OR UPDATE OR DELETE ON invoice_receivable_attestation_runs FOR EACH ROW EXECUTE FUNCTION db135_guard_run()")
    op.execute("""CREATE FUNCTION db135_guard_attestation() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE prior invoice_receivable_attestations%ROWTYPE; entry jsonb;
    BEGIN
      IF TG_OP <> 'INSERT' THEN RAISE EXCEPTION 'DB135 attestation evidence is immutable'; END IF;
      IF NOT EXISTS (SELECT 1 FROM invoices i JOIN repair_orders ro ON ro.id = i.repair_order_id
                     WHERE i.id = NEW.invoice_id AND i.tenant_id = NEW.tenant_id
                       AND i.repair_order_id = NEW.repair_order_id AND ro.tenant_id = NEW.tenant_id
                       AND NEW.customer_id = COALESCE(i.billed_customer_id, ro.customer_id)) THEN
        RAISE EXCEPTION 'DB135 invoice lineage mismatch';
      END IF;
      SELECT r.approved_entries -> NEW.invoice_id::text INTO entry FROM invoice_receivable_attestation_runs r
                     WHERE r.id = NEW.run_id AND r.tenant_id = NEW.tenant_id
                       AND r.manifest_digest = NEW.manifest_digest
                       AND r.reviewer_user_id = NEW.reviewer_user_id
                       AND r.executor_user_id = NEW.executor_user_id
                       AND r.fingerprint_version = NEW.fingerprint_version
                       AND r.invoice_ids ? NEW.invoice_id::text;
      IF entry IS NULL
         OR entry->>'decision' IS DISTINCT FROM NEW.decision
         OR entry->>'repair_order_id' IS DISTINCT FROM NEW.repair_order_id::text
         OR entry->>'customer_id' IS DISTINCT FROM NEW.customer_id::text
         OR entry->>'principal_total_cents' IS DISTINCT FROM NEW.principal_total_cents::text
         OR entry->>'confirmed_principal_cents' IS DISTINCT FROM NEW.confirmed_principal_cents::text
         OR entry->>'source_fingerprint' IS DISTINCT FROM NEW.source_fingerprint
         OR entry->>'evidence_digest' IS DISTINCT FROM NEW.evidence_digest
         OR entry->>'fingerprint_version' IS DISTINCT FROM NEW.fingerprint_version
         OR entry->>'version' IS DISTINCT FROM NEW.version::text
         OR entry->>'supersedes_id' IS DISTINCT FROM COALESCE(NEW.supersedes_id::text, '')
         OR entry->>'reviewed_at' IS DISTINCT FROM to_char(NEW.reviewed_at AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.US"Z"')
         OR entry->>'valid_until' IS DISTINCT FROM to_char(NEW.valid_until AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.US"Z"')
         OR entry->>'audit_reference' IS DISTINCT FROM NEW.audit_reference THEN
        RAISE EXCEPTION 'DB135 run lineage mismatch';
      END IF;
      IF NEW.applied_at < transaction_timestamp() OR NEW.applied_at > clock_timestamp() + interval '1 minute' THEN
        RAISE EXCEPTION 'DB135 apply time mismatch';
      END IF;
      IF NEW.supersedes_id IS NOT NULL THEN
        SELECT * INTO prior FROM invoice_receivable_attestations WHERE id = NEW.supersedes_id;
        IF NOT FOUND OR prior.tenant_id <> NEW.tenant_id OR prior.invoice_id <> NEW.invoice_id
           OR prior.version + 1 <> NEW.version THEN
          RAISE EXCEPTION 'DB135 predecessor mismatch';
        END IF;
      END IF;
      RETURN NEW;
    END $$""")
    op.execute("CREATE TRIGGER trg_db135_attestation_guard BEFORE INSERT OR UPDATE OR DELETE ON invoice_receivable_attestations FOR EACH ROW EXECUTE FUNCTION db135_guard_attestation()")
    op.execute("""CREATE FUNCTION db135_check_run_count() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE run_id_to_check uuid; expected integer; actual integer;
    BEGIN
      run_id_to_check := CASE WHEN TG_TABLE_NAME = 'invoice_receivable_attestation_runs' THEN NEW.id ELSE NEW.run_id END;
      SELECT r.expected_insert_count INTO expected FROM invoice_receivable_attestation_runs r WHERE r.id = run_id_to_check;
      SELECT count(*) INTO actual FROM invoice_receivable_attestations a WHERE a.run_id = run_id_to_check;
      IF expected IS DISTINCT FROM actual THEN RAISE EXCEPTION 'DB135 run insert count mismatch'; END IF;
      RETURN NULL;
    END $$""")
    op.execute("CREATE CONSTRAINT TRIGGER trg_db135_run_complete AFTER INSERT ON invoice_receivable_attestation_runs DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION db135_check_run_count()")


def downgrade():
    bind = op.get_bind()
    if bind.execute(sa.text("SELECT 1 FROM invoice_receivable_attestations LIMIT 1")).first() or bind.execute(sa.text("SELECT 1 FROM invoice_receivable_attestation_runs LIMIT 1")).first():
        raise RuntimeError("DB135 downgrade refused: receivable attestation evidence exists")
    op.drop_table("invoice_receivable_attestations")
    op.drop_table("invoice_receivable_attestation_runs")
    op.execute("DROP FUNCTION db135_guard_attestation()")
    op.execute("DROP FUNCTION db135_guard_run()")
    op.execute("DROP FUNCTION db135_check_run_count()")
