"""Immutable purpose-encrypted customer EFS instrument claims, no backfill."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
revision='203_customer_efs_submissions'
down_revision='202_fleet_asset_attachments'
branch_labels=None
depends_on=None

LEGACY_FLEET_GUARD = """CREATE OR REPLACE FUNCTION guard_db048_fleet_evidence() RETURNS trigger LANGUAGE plpgsql AS $$
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
      END $$"""

PROTECTED_FLEET_GUARD = """CREATE OR REPLACE FUNCTION guard_db048_fleet_evidence() RETURNS trigger LANGUAGE plpgsql AS $$
      BEGIN
        IF TG_OP = 'UPDATE' AND OLD.rail = 'fleet_payment'
          AND NEW.manual_evidence IS DISTINCT FROM OLD.manual_evidence THEN
          RAISE EXCEPTION 'Fleet instrument evidence is immutable';
        END IF;
        IF NEW.source = 'customer_efs_v1' THEN
          IF NEW.rail <> 'fleet_payment' OR NEW.provider <> 'manual'
            OR NEW.card_fee_amount <> 0 OR NEW.card_fee_tax_amount <> 0 OR NEW.processor_fee_amount <> 0
            OR jsonb_typeof(NEW.manual_evidence::jsonb) IS DISTINCT FROM 'object'
            OR NEW.manual_evidence->>'source' IS DISTINCT FROM 'customer_efs_v1'
            OR NEW.manual_evidence->>'fleet_provider' IS DISTINCT FROM 'EFS'
            OR COALESCE(NEW.manual_evidence->>'efs_submission_id','') !~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
            OR COALESCE(NEW.manual_evidence->>'code_last4','') !~ '^[0-9]{4}$'
            OR (NEW.manual_evidence::jsonb - ARRAY['source','fleet_provider','efs_submission_id','code_last4']) <> '{}'::jsonb
          THEN RAISE EXCEPTION 'Protected EFS evidence is invalid'; END IF;
          RETURN NEW;
        END IF;
        IF NEW.manual_evidence::jsonb ? 'efs_submission_id' THEN
          RAISE EXCEPTION 'Protected EFS marker requires its dedicated source';
        END IF;
        IF NEW.rail = 'fleet_payment' AND (
          jsonb_typeof(NEW.manual_evidence::jsonb) IS DISTINCT FROM 'object'
          OR COALESCE(NEW.manual_evidence->>'fleet_provider', '') NOT IN ('EFS','Comchek','T-Chek','Other')
          OR length(trim(COALESCE(NEW.manual_evidence->>'reference_number', ''))) NOT BETWEEN 1 AND 255
          OR (NEW.manual_evidence->>'fleet_provider' = 'Other' AND
              length(trim(COALESCE(NEW.manual_evidence->>'fleet_provider_name', ''))) NOT BETWEEN 1 AND 100)
        ) THEN RAISE EXCEPTION 'Fleet provider and instrument reference are required'; END IF;
        RETURN NEW;
      END $$"""

def upgrade():
    op.create_unique_constraint('uq_invoice_settlements_tenant_id','invoice_settlements',['tenant_id','id'])
    op.create_unique_constraint('uq_invoice_attempts_tenant_id','invoice_payment_attempts',['tenant_id','id'])
    op.create_table('efs_instrument_submissions',
        sa.Column('id',postgresql.UUID(as_uuid=True),primary_key=True),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False,server_default=sa.func.now()),
        sa.Column('updated_at',sa.DateTime(timezone=True),nullable=False,server_default=sa.func.now()),
        sa.Column('deleted_at',sa.DateTime(timezone=True)),
        sa.Column('tenant_id',postgresql.UUID(as_uuid=True),sa.ForeignKey('tenants.id'),nullable=False),
        *[sa.Column(name,postgresql.UUID(as_uuid=True),nullable=False) for name in ('invoice_id','settlement_id','attempt_id','customer_id')],
        sa.Column('provider',sa.String(8),nullable=False),sa.Column('secret_ciphertext',sa.Text(),nullable=False),
        sa.Column('key_version',sa.String(32),nullable=False),sa.Column('code_fingerprint',sa.String(64),nullable=False),sa.Column('fingerprint_key_identity',sa.String(64),nullable=False),
        sa.Column('last4',sa.String(4),nullable=False),sa.Column('submission_request_sha256',sa.String(64),nullable=False),
        sa.UniqueConstraint('attempt_id',name='uq_efs_submission_attempt'),
        sa.UniqueConstraint('tenant_id','provider','code_fingerprint',name='uq_efs_tenant_instrument'),
        sa.CheckConstraint("provider='EFS' AND length(code_fingerprint)=64 AND length(fingerprint_key_identity)=64 AND last4 ~ '^[0-9]{4}$' AND length(submission_request_sha256)=64 AND deleted_at IS NULL",name='ck_efs_claim_shape'),
        *[sa.ForeignKeyConstraint(['tenant_id',name], [table+'.tenant_id',table+'.id'],name=constraint) for name,table,constraint in [('invoice_id','invoices','fk_efs_invoice'),('customer_id','customers','fk_efs_customer'),('attempt_id','invoice_payment_attempts','fk_efs_attempt'),('settlement_id','invoice_settlements','fk_efs_settlement')]],
    )
    op.create_index('ix_efs_instrument_submissions_tenant_id','efs_instrument_submissions',['tenant_id'])
    op.execute('''CREATE FUNCTION efs_claim_guard() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF TG_OP <> 'INSERT' THEN RAISE EXCEPTION 'EFS instrument claims are immutable'; END IF;
      IF NOT EXISTS (SELECT 1 FROM invoice_payment_attempts a JOIN invoice_settlements s ON s.id=a.settlement_id AND s.tenant_id=a.tenant_id
        JOIN invoices i ON i.id=a.invoice_id AND i.tenant_id=a.tenant_id
        JOIN repair_orders r ON r.id=i.repair_order_id AND r.tenant_id=i.tenant_id
        WHERE a.id=NEW.attempt_id AND a.tenant_id=NEW.tenant_id AND a.invoice_id=NEW.invoice_id AND a.settlement_id=NEW.settlement_id AND a.customer_id=NEW.customer_id
        AND s.invoice_id=NEW.invoice_id AND s.customer_id=NEW.customer_id AND COALESCE(i.billed_customer_id,r.customer_id)=NEW.customer_id
        AND a.source='customer_efs_v1' AND a.rail='fleet_payment' AND a.provider='manual'
        AND a.manual_evidence->>'efs_submission_id'=NEW.id::text AND a.manual_evidence->>'fleet_provider'='EFS' AND a.manual_evidence->>'code_last4'=NEW.last4)
      THEN RAISE EXCEPTION 'EFS claim binding is invalid'; END IF;
      RETURN NEW;
    END $$''')
    op.execute('CREATE TRIGGER efs_claim_guard BEFORE INSERT OR UPDATE OR DELETE ON efs_instrument_submissions FOR EACH ROW EXECUTE FUNCTION efs_claim_guard()')
    # Keep legacy146 evidence immutable and unchanged for every old Fleet path.
    # Protected inserts may precede their encrypted claim only inside this txn.
    op.execute(PROTECTED_FLEET_GUARD)
    op.execute("""CREATE FUNCTION require_efs_attempt_claim() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF NEW.source='customer_efs_v1' AND NOT EXISTS (
        SELECT 1 FROM efs_instrument_submissions c WHERE c.attempt_id=NEW.id
          AND c.tenant_id=NEW.tenant_id AND c.invoice_id=NEW.invoice_id
          AND c.settlement_id=NEW.settlement_id AND c.customer_id=NEW.customer_id
          AND c.id::text=NEW.manual_evidence->>'efs_submission_id'
          AND c.provider='EFS' AND c.last4=NEW.manual_evidence->>'code_last4'
      ) THEN RAISE EXCEPTION 'Protected EFS request requires its exact encrypted claim'; END IF;
      RETURN NEW;
    END $$""")
    op.execute('CREATE CONSTRAINT TRIGGER check_efs_attempt_claim AFTER INSERT OR UPDATE ON invoice_payment_attempts DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION require_efs_attempt_claim()')


def downgrade():
    op.execute("DO $$ BEGIN IF EXISTS(SELECT 1 FROM efs_instrument_submissions) THEN RAISE EXCEPTION 'EFS claims must be retained'; END IF; END $$")
    op.execute('DROP TRIGGER IF EXISTS check_efs_attempt_claim ON invoice_payment_attempts')
    op.execute('DROP FUNCTION IF EXISTS require_efs_attempt_claim()')
    op.execute(LEGACY_FLEET_GUARD)
    op.drop_table('efs_instrument_submissions');op.execute('DROP FUNCTION efs_claim_guard()')
    op.drop_constraint('uq_invoice_attempts_tenant_id','invoice_payment_attempts',type_='unique')
    op.drop_constraint('uq_invoice_settlements_tenant_id','invoice_settlements',type_='unique')
