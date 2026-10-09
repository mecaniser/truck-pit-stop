"""Durable driver worker source, attempts and append-only recovery receipts."""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

from alembic import op

revision = "164_motive_driver_journal"
down_revision = "163_fleet_driver_records"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "motive_driver_worker_runs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("worker_key", sa.String(120), nullable=False),
        sa.Column(
            "tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False
        ),
        sa.Column(
            "actor_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False
        ),
        sa.Column("fleet_customer_id", UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", sa.String(120), nullable=False),
        sa.Column("company_label", sa.String(255), nullable=False),
        sa.Column("mode", sa.String(16), nullable=False),
        sa.Column("source_sha256", sa.String(64), nullable=False),
        sa.Column("source_document", JSONB, nullable=False),
        sa.Column("attempt_document", JSONB),
        sa.Column("attempt_sha256", sa.String(64)),
        sa.Column("stage", sa.String(20), nullable=False),
        sa.Column("receipts", JSONB, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "fleet_customer_id"], ["customers.tenant_id", "customers.id"]
        ),
        sa.CheckConstraint(
            "mode IN ('commit', 'dry_run')", name="ck_driver_journal_mode"
        ),
        sa.CheckConstraint(
            "stage IN ('source_saved', 'validated', 'commit_pending', 'committed', 'verified')",
            name="ck_driver_journal_stage",
        ),
        sa.CheckConstraint(
            "source_sha256 ~ '^[a-f0-9]{64}$'", name="ck_driver_journal_source_hash"
        ),
        sa.CheckConstraint(
            "jsonb_typeof(source_document) = 'object' AND octet_length(source_document::text) <= 16777216",
            name="ck_driver_journal_source_size",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(receipts) = 'array' AND jsonb_array_length(receipts) > 0 AND receipts->-1->>'stage' IS NOT NULL AND receipts->-1->>'stage' = stage",
            name="ck_driver_journal_receipts",
        ),
        sa.CheckConstraint(
            "(attempt_document IS NULL AND attempt_sha256 IS NULL AND stage='source_saved') OR (attempt_document IS NOT NULL AND attempt_sha256 IS NOT NULL AND jsonb_typeof(attempt_document)='object' AND attempt_sha256 ~ '^[a-f0-9]{64}$' AND stage<>'source_saved')",
            name="ck_driver_journal_attempt",
        ),
        sa.CheckConstraint(
            "mode='commit' OR stage IN ('source_saved', 'validated')",
            name="ck_driver_journal_dry_run",
        ),
    )
    op.create_index(
        "ix_driver_journal_worker_pending",
        "motive_driver_worker_runs",
        ["worker_key", "mode", "stage", "created_at"],
    )
    op.execute("""
        CREATE FUNCTION guard_motive_driver_journal() RETURNS trigger AS $$
        DECLARE i integer;
        BEGIN
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'Driver journal evidence is append only';
            END IF;
            IF NOT EXISTS (SELECT 1 FROM users WHERE id=NEW.actor_id AND tenant_id=NEW.tenant_id) THEN
                RAISE EXCEPTION 'Driver journal actor tenant mismatch';
            END IF;
            IF TG_OP = 'INSERT' THEN
                IF NEW.stage <> 'source_saved' OR NEW.attempt_document IS NOT NULL OR jsonb_array_length(NEW.receipts) <> 1 THEN
                    RAISE EXCEPTION 'Driver journal must begin at source_saved';
                END IF;
                RETURN NEW;
            END IF;
            IF ROW(NEW.id, NEW.worker_key, NEW.tenant_id, NEW.actor_id, NEW.fleet_customer_id, NEW.company_id, NEW.company_label, NEW.mode, NEW.source_sha256, NEW.source_document, NEW.created_at)
                IS DISTINCT FROM ROW(OLD.id, OLD.worker_key, OLD.tenant_id, OLD.actor_id, OLD.fleet_customer_id, OLD.company_id, OLD.company_label, OLD.mode, OLD.source_sha256, OLD.source_document, OLD.created_at) THEN
                RAISE EXCEPTION 'Driver journal source identity is immutable';
            END IF;
            IF OLD.attempt_document IS NOT NULL AND ROW(NEW.attempt_document, NEW.attempt_sha256) IS DISTINCT FROM ROW(OLD.attempt_document, OLD.attempt_sha256) THEN
                RAISE EXCEPTION 'Driver journal attempt is immutable';
            END IF;
            IF OLD.stage = 'verified' OR jsonb_array_length(NEW.receipts) <> jsonb_array_length(OLD.receipts) + 1 THEN
                RAISE EXCEPTION 'Driver journal receipt must append one phase';
            END IF;
            IF NOT (
                (OLD.stage='source_saved' AND NEW.stage='validated') OR
                (OLD.stage='validated' AND NEW.stage IN ('validated','commit_pending')) OR
                (OLD.stage='commit_pending' AND NEW.stage IN ('validated','committed')) OR
                (OLD.stage='committed' AND NEW.stage IN ('validated','verified'))
            ) THEN
                RAISE EXCEPTION 'Driver journal phase transition is invalid';
            END IF;
            FOR i IN 0..jsonb_array_length(OLD.receipts)-1 LOOP
                IF NEW.receipts->i IS DISTINCT FROM OLD.receipts->i THEN
                    RAISE EXCEPTION 'Driver journal receipt history is immutable';
                END IF;
            END LOOP;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
    """)
    op.execute(
        "CREATE TRIGGER trg_motive_driver_journal BEFORE INSERT OR UPDATE OR DELETE ON motive_driver_worker_runs FOR EACH ROW EXECUTE FUNCTION guard_motive_driver_journal()"
    )


def downgrade():
    op.execute(
        "DO $$ BEGIN IF EXISTS (SELECT 1 FROM motive_driver_worker_runs) THEN RAISE EXCEPTION 'Retain revision 164: driver recovery evidence exists'; END IF; END $$"
    )
    op.drop_table("motive_driver_worker_runs")
    op.execute("DROP FUNCTION guard_motive_driver_journal()")
