"""Immutable booking prepayment application and external accounting review.

Revision ID: 200
Revises: 199
"""
from alembic import op
import sqlalchemy as sa
revision='200'
down_revision='199_booking_fulfillment'
branch_labels=None
depends_on=None

def upgrade():
    op.add_column('booking_receipts',sa.Column('version',sa.Integer(),nullable=False,server_default='1'))
    op.add_column('booking_payment_events',sa.Column('verified_refund_amount_minor',sa.BigInteger(),nullable=True))
    op.add_column('booking_payment_events',sa.Column('verified_refund_delta_minor',sa.BigInteger(),nullable=True))
    op.add_column('booking_payment_events',sa.Column('client_idempotency_key',sa.String(200),nullable=True))
    op.add_column('booking_payment_events',sa.Column('provider_refund_reference',sa.String(255),nullable=True))
    op.add_column('booking_payment_events',sa.Column('request_sha256',sa.String(64),nullable=True))
    op.create_unique_constraint('uq_booking_event_client_command','booking_payment_events',['tenant_id','client_idempotency_key'])
    op.create_check_constraint('ck_booking_event_command_pair','booking_payment_events',"(client_idempotency_key IS NULL AND request_sha256 IS NULL) OR (client_idempotency_key IS NOT NULL AND length(request_sha256)=64)")
    op.add_column('booking_payment_events',sa.Column('verified_dispute_amount_minor',sa.BigInteger(),nullable=True))
    op.create_check_constraint('ck_booking_event_refund_delta','booking_payment_events','verified_refund_delta_minor IS NULL OR verified_refund_delta_minor>0')
    op.create_check_constraint('ck_booking_event_dispute_amount','booking_payment_events','verified_dispute_amount_minor IS NULL OR verified_dispute_amount_minor>0')
    op.create_check_constraint('ck_booking_event_refund_amount','booking_payment_events','verified_refund_amount_minor IS NULL OR verified_refund_amount_minor>=0')
    op.create_check_constraint('ck_booking_receipt_version','booking_receipts','version>=1')
    op.create_index('ix_booking_receipt_tenant_received','booking_receipts',['tenant_id','received_at'])
    op.execute("""CREATE OR REPLACE FUNCTION guard_booking_receipt() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
      IF (to_jsonb(OLD)-ARRAY['updated_at','refunded_amount_minor','version']) IS DISTINCT FROM (to_jsonb(NEW)-ARRAY['updated_at','refunded_amount_minor','version']) OR NEW.refunded_amount_minor<OLD.refunded_amount_minor OR NEW.version NOT IN (OLD.version,OLD.version+1) THEN RAISE EXCEPTION 'booking receipt proof is immutable'; END IF;
      RETURN NEW; END; $$""")

    op.execute("CREATE TABLE booking_receipt_applications (\n\ttenant_id UUID NOT NULL, \n\treceipt_id UUID NOT NULL, \n\tappointment_id UUID NOT NULL, \n\trepair_order_id UUID NOT NULL, \n\tinvoice_id UUID NOT NULL, \n\tsettlement_id UUID NOT NULL, \n\tcustomer_id UUID NOT NULL, \n\tamount_minor BIGINT NOT NULL, \n\tcurrency VARCHAR(3) NOT NULL, \n\treceipt_version_before INTEGER NOT NULL, \n\tbooking_version_before INTEGER NOT NULL, \n\tprovider VARCHAR(32) NOT NULL, \n\tprovider_account_id VARCHAR(255) NOT NULL, \n\tenvironment VARCHAR(24) NOT NULL, \n\tconfiguration_version INTEGER NOT NULL, \n\tqbo_realm_snapshot VARCHAR(255), \n\treceipt_proof_sha256 VARCHAR(64) NOT NULL, \n\tinvoice_economics_sha256 VARCHAR(64) NOT NULL, \n\tactor_user_id UUID NOT NULL, \n\tactor_name_snapshot VARCHAR(255) NOT NULL, \n\tidempotency_key VARCHAR(200) NOT NULL, \n\trequest_sha256 VARCHAR(64) NOT NULL, \n\tid UUID NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tdeleted_at TIMESTAMP WITH TIME ZONE, \n\tPRIMARY KEY (id), \n\tCONSTRAINT uq_booking_application_tenant_id UNIQUE (tenant_id, id), \n\tCONSTRAINT uq_booking_application_key UNIQUE (tenant_id, idempotency_key), \n\tFOREIGN KEY(tenant_id, receipt_id) REFERENCES booking_receipts (tenant_id, id), \n\tFOREIGN KEY(tenant_id, appointment_id) REFERENCES appointments (tenant_id, id), \n\tFOREIGN KEY(tenant_id, repair_order_id) REFERENCES repair_orders (tenant_id, id), \n\tFOREIGN KEY(tenant_id, invoice_id) REFERENCES invoices (tenant_id, id), \n\tFOREIGN KEY(tenant_id, customer_id) REFERENCES customers (tenant_id, id), \n\tFOREIGN KEY(tenant_id, configuration_version) REFERENCES tenant_payment_provider_configurations (tenant_id, version), \n\tCONSTRAINT ck_booking_application_amount CHECK (amount_minor>0 AND currency='usd'), \n\tCONSTRAINT ck_booking_application_versions CHECK (receipt_version_before>=1 AND booking_version_before>=1), \n\tCONSTRAINT ck_booking_application_provider CHECK (environment IN ('sandbox','production') AND provider IN ('quickbooks_payments','stripe_connect')), \n\tFOREIGN KEY(tenant_id) REFERENCES tenants (id), \n\tFOREIGN KEY(settlement_id) REFERENCES invoice_settlements (id), \n\tFOREIGN KEY(actor_user_id) REFERENCES users (id)\n)")
    op.execute('CREATE INDEX ix_booking_receipt_applications_receipt_id ON booking_receipt_applications (receipt_id)')
    op.execute('CREATE INDEX ix_booking_receipt_applications_id ON booking_receipt_applications (id)')
    op.execute('CREATE INDEX ix_booking_receipt_applications_tenant_id ON booking_receipt_applications (tenant_id)')
    op.execute('CREATE INDEX ix_booking_receipt_applications_invoice_id ON booking_receipt_applications (invoice_id)')
    op.execute("CREATE TABLE booking_accounting_review_tasks (\n\ttenant_id UUID NOT NULL, \n\treceipt_id UUID NOT NULL, \n\tapplication_id UUID, \n\tinvoice_id UUID, \n\tobject_kind VARCHAR(40) NOT NULL, \n\tfinancial_object_id UUID NOT NULL, \n\toperation_version INTEGER NOT NULL, \n\tstate VARCHAR(32) NOT NULL, \n\tversion INTEGER NOT NULL, \n\tprovider VARCHAR(32) NOT NULL, \n\tprovider_account_id VARCHAR(255) NOT NULL, \n\tenvironment VARCHAR(24) NOT NULL, \n\tconfiguration_version INTEGER NOT NULL, \n\tqbo_realm_snapshot VARCHAR(255), \n\tamount_minor BIGINT NOT NULL, \n\tcurrency VARCHAR(3) NOT NULL, \n\towning_writer VARCHAR(24) NOT NULL, \n\tevidence_snapshot_sha256 VARCHAR(64) NOT NULL, \n\tid UUID NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tdeleted_at TIMESTAMP WITH TIME ZONE, \n\tPRIMARY KEY (id), \n\tCONSTRAINT uq_booking_review_task_tenant_id UNIQUE (tenant_id, id), \n\tCONSTRAINT uq_booking_review_object UNIQUE (tenant_id, object_kind, financial_object_id, operation_version), \n\tFOREIGN KEY(tenant_id, receipt_id) REFERENCES booking_receipts (tenant_id, id), \n\tFOREIGN KEY(tenant_id, application_id) REFERENCES booking_receipt_applications (tenant_id, id), \n\tFOREIGN KEY(tenant_id, invoice_id) REFERENCES invoices (tenant_id, id), \n\tCONSTRAINT ck_booking_review_kind CHECK (object_kind IN ('booking_receipt_liability','booking_receipt_application')), \n\tCONSTRAINT ck_booking_review_state CHECK (state IN ('awaiting_manual_ack','externally_reconciled','needs_review')), \n\tCONSTRAINT ck_booking_review_money CHECK (amount_minor>0 AND currency='usd' AND owning_writer='external_manual'), \n\tCONSTRAINT ck_booking_review_version CHECK (version>=1 AND operation_version>=1), \n\tCONSTRAINT ck_booking_review_object_binding CHECK ((object_kind='booking_receipt_liability' AND application_id IS NULL AND invoice_id IS NULL AND financial_object_id=receipt_id) OR (object_kind='booking_receipt_application' AND application_id IS NOT NULL AND invoice_id IS NOT NULL AND financial_object_id=application_id)), \n\tFOREIGN KEY(tenant_id) REFERENCES tenants (id)\n)")
    op.execute('CREATE INDEX ix_booking_accounting_review_tasks_receipt_id ON booking_accounting_review_tasks (receipt_id)')
    op.execute('CREATE INDEX ix_booking_accounting_review_tasks_invoice_id ON booking_accounting_review_tasks (invoice_id)')
    op.execute('CREATE INDEX ix_booking_accounting_review_tasks_id ON booking_accounting_review_tasks (id)')
    op.execute('CREATE INDEX ix_booking_accounting_review_tasks_tenant_id ON booking_accounting_review_tasks (tenant_id)')
    op.execute("CREATE TABLE booking_accounting_review_events (\n\ttenant_id UUID NOT NULL, \n\ttask_id UUID NOT NULL, \n\tactor_user_id UUID, \n\tactor_name_snapshot VARCHAR(255) NOT NULL, \n\tbefore_state VARCHAR(32) NOT NULL, \n\tafter_state VARCHAR(32) NOT NULL, \n\tevidence_reference TEXT NOT NULL, \n\texternal_company_reference VARCHAR(255) NOT NULL, \n\treview_note TEXT NOT NULL, \n\tidempotency_key VARCHAR(200) NOT NULL, \n\trequest_sha256 VARCHAR(64) NOT NULL, \n\tid UUID NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tdeleted_at TIMESTAMP WITH TIME ZONE, \n\tPRIMARY KEY (id), \n\tFOREIGN KEY(tenant_id, task_id) REFERENCES booking_accounting_review_tasks (tenant_id, id), \n\tCONSTRAINT uq_booking_review_ack_key UNIQUE (tenant_id, idempotency_key), \n\tCONSTRAINT ck_booking_review_ack_state CHECK (after_state IN ('externally_reconciled','needs_review')), \n\tFOREIGN KEY(tenant_id) REFERENCES tenants (id), \n\tFOREIGN KEY(actor_user_id) REFERENCES users (id)\n)")
    op.execute('CREATE INDEX ix_booking_accounting_review_events_id ON booking_accounting_review_events (id)')
    op.add_column('booking_accounting_review_events',sa.Column('source_event_id',sa.UUID(),sa.ForeignKey('booking_payment_events.id'),nullable=True))
    op.add_column('booking_accounting_review_events',sa.Column('receipt_liability_recorded',sa.Boolean(),nullable=False))
    op.add_column('booking_accounting_review_events',sa.Column('application_to_ar_recorded',sa.Boolean(),nullable=False))
    op.execute("""CREATE FUNCTION guard_booking_application_insert() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE r booking_receipts%ROWTYPE; a appointments%ROWTYPE; i invoices%ROWTYPE;
      s invoice_settlements%ROWTYPE; p booking_payment_attempts%ROWTYPE; c tenant_payment_provider_configurations%ROWTYPE; used bigint;
    BEGIN
      SELECT * INTO r FROM booking_receipts WHERE id=NEW.receipt_id AND tenant_id=NEW.tenant_id FOR UPDATE;
      SELECT * INTO a FROM appointments WHERE id=NEW.appointment_id AND tenant_id=NEW.tenant_id;
      SELECT * INTO i FROM invoices WHERE id=NEW.invoice_id AND tenant_id=NEW.tenant_id;
      SELECT * INTO s FROM invoice_settlements WHERE id=NEW.settlement_id AND tenant_id=NEW.tenant_id;
      SELECT * INTO p FROM booking_payment_attempts WHERE id=r.attempt_id AND tenant_id=NEW.tenant_id;
      SELECT * INTO c FROM tenant_payment_provider_configurations WHERE tenant_id=NEW.tenant_id AND version=p.configuration_version;
      IF c.id IS NULL OR r.id IS NULL OR a.id IS NULL OR i.id IS NULL OR s.id IS NULL OR p.id IS NULL
        OR r.appointment_id<>a.id OR a.repair_order_id IS DISTINCT FROM NEW.repair_order_id
        OR i.repair_order_id<>NEW.repair_order_id OR s.invoice_id<>i.id OR s.customer_id<>NEW.customer_id
        OR a.customer_id<>NEW.customer_id OR COALESCE(i.billed_customer_id,a.customer_id)<>NEW.customer_id
        OR a.booking_payment_version<>1 OR a.booking_payment_state<>'paid' OR a.status::text NOT IN ('confirmed','in_progress','completed')
        OR r.provider<>p.provider OR r.provider_account_id<>p.provider_account_id
        OR c.selected_provider<>p.provider OR c.provider_account_snapshot IS DISTINCT FROM p.provider_account_id
        OR c.qbo_realm_snapshot IS DISTINCT FROM NEW.qbo_realm_snapshot
        OR a.booking_provider_configuration_version<>p.configuration_version OR a.booking_provider_environment<>p.environment
        OR EXISTS(SELECT 1 FROM booking_payment_attempts pending WHERE pending.tenant_id=NEW.tenant_id AND pending.appointment_id=a.id AND pending.state IN ('created','creating','requires_action','requires_payment_method','processing','outcome_unknown'))
        OR p.state<>'succeeded' OR p.verified_at IS NULL OR r.proof_sha256<>NEW.receipt_proof_sha256
        OR p.provider<>NEW.provider OR p.provider_account_id<>NEW.provider_account_id
        OR p.environment<>NEW.environment OR p.configuration_version<>NEW.configuration_version
        OR r.currency<>NEW.currency OR r.provider_intent_id IS DISTINCT FROM p.provider_intent_id
        OR r.charge_id IS NULL OR length(r.charge_id)=0 OR p.provider_charge_id IS NULL OR length(p.provider_charge_id)=0
        OR r.charge_id IS DISTINCT FROM p.provider_charge_id
        OR NEW.receipt_version_before<>r.version OR NEW.booking_version_before<>a.booking_version
        OR NOT EXISTS(SELECT 1 FROM repair_orders ro WHERE ro.id=NEW.repair_order_id AND ro.tenant_id=NEW.tenant_id AND ro.customer_id=NEW.customer_id)
        OR NOT EXISTS(SELECT 1 FROM users u WHERE u.id=NEW.actor_user_id AND u.tenant_id=NEW.tenant_id AND u.is_active AND u.deleted_at IS NULL AND u.role::text IN ('garage_owner','garage_admin','receptionist'))
        THEN RAISE EXCEPTION 'invalid booking application binding'; END IF;
      SELECT COALESCE(SUM(amount_minor),0) INTO used FROM booking_receipt_applications WHERE receipt_id=r.id AND tenant_id=NEW.tenant_id;
      IF used+NEW.amount_minor+r.refunded_amount_minor>r.amount_received_minor THEN RAISE EXCEPTION 'booking liability overapplication'; END IF;
      SELECT COALESCE(SUM(amount_minor),0) INTO used FROM booking_receipt_applications WHERE invoice_id=i.id AND tenant_id=NEW.tenant_id;
      IF used+NEW.amount_minor>s.principal_total*100 THEN RAISE EXCEPTION 'booking invoice overapplication'; END IF;
      RETURN NEW;
    END $$""")
    op.execute('CREATE TRIGGER booking_application_exact_binding BEFORE INSERT ON booking_receipt_applications FOR EACH ROW EXECUTE FUNCTION guard_booking_application_insert()')
    op.execute("""CREATE FUNCTION guard_booking_application_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
      BEGIN RAISE EXCEPTION 'booking application evidence is append-only'; END $$""")
    for table in ('booking_receipt_applications','booking_accounting_review_events'):
        op.execute(f'CREATE TRIGGER immutable_{table} BEFORE UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION guard_booking_application_immutable()')
    op.execute("""CREATE FUNCTION guard_booking_accounting_task() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF TG_OP='DELETE' THEN RAISE EXCEPTION 'booking accounting task cannot be deleted'; END IF;
      IF TG_OP='UPDATE' AND (to_jsonb(OLD)-ARRAY['state','version','updated_at']) IS DISTINCT FROM (to_jsonb(NEW)-ARRAY['state','version','updated_at']) THEN RAISE EXCEPTION 'booking accounting provenance immutable'; END IF;
      IF TG_OP='UPDATE' AND (NEW.version<>OLD.version+1 OR NOT ((OLD.state='awaiting_manual_ack' AND NEW.state IN ('externally_reconciled','needs_review')) OR (OLD.state='externally_reconciled' AND NEW.state='needs_review'))) THEN RAISE EXCEPTION 'invalid accounting task transition'; END IF;
      IF NOT EXISTS(SELECT 1 FROM booking_receipts r JOIN booking_payment_attempts p ON p.id=r.attempt_id AND p.tenant_id=r.tenant_id WHERE r.id=NEW.receipt_id AND r.tenant_id=NEW.tenant_id AND r.provider=NEW.provider AND r.provider_account_id=NEW.provider_account_id AND p.environment=NEW.environment AND p.configuration_version=NEW.configuration_version AND (NEW.object_kind<>'booking_receipt_liability' OR r.amount_received_minor=NEW.amount_minor)) THEN RAISE EXCEPTION 'invalid receipt task binding'; END IF;
      IF NEW.application_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM booking_receipt_applications a WHERE a.id=NEW.application_id AND a.tenant_id=NEW.tenant_id AND a.receipt_id=NEW.receipt_id AND a.invoice_id=NEW.invoice_id AND a.amount_minor=NEW.amount_minor) THEN RAISE EXCEPTION 'invalid application task binding'; END IF;
      RETURN NEW;
    END $$""")
    op.execute('CREATE TRIGGER booking_accounting_task_guard BEFORE INSERT OR UPDATE OR DELETE ON booking_accounting_review_tasks FOR EACH ROW EXECUTE FUNCTION guard_booking_accounting_task()')
    op.execute("""CREATE FUNCTION guard_booking_accounting_ack() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF NEW.after_state='needs_review' THEN
        IF NEW.actor_user_id IS NOT NULL OR NEW.source_event_id IS NULL OR NEW.receipt_liability_recorded OR NEW.application_to_ar_recorded OR NOT EXISTS(
          SELECT 1 FROM booking_payment_events e JOIN booking_accounting_review_tasks t ON t.id=NEW.task_id AND t.tenant_id=NEW.tenant_id
          JOIN booking_receipts r ON r.id=t.receipt_id AND r.tenant_id=t.tenant_id
          WHERE e.id=NEW.source_event_id AND e.tenant_id=NEW.tenant_id AND e.appointment_id=r.appointment_id AND e.attempt_id=r.attempt_id
            AND e.provider=r.provider AND e.provider_account_id=r.provider_account_id AND length(e.proof_sha256)=64
            AND e.source IN ('server_retrieval','verified_connect_webhook')) THEN RAISE EXCEPTION 'invalid accounting review source evidence'; END IF;
        RETURN NEW;
      END IF;
      IF NEW.source_event_id IS NOT NULL THEN RAISE EXCEPTION 'staff acknowledgment cannot substitute provider event'; END IF;
      IF NOT EXISTS(SELECT 1 FROM users u WHERE u.id=NEW.actor_user_id AND u.tenant_id=NEW.tenant_id AND u.is_active AND u.deleted_at IS NULL AND u.role::text IN ('garage_owner','garage_admin')) OR length(trim(NEW.evidence_reference))=0 OR length(trim(NEW.external_company_reference))=0 OR length(trim(NEW.review_note))=0 THEN RAISE EXCEPTION 'invalid booking accounting acknowledgment'; END IF;
      IF NOT EXISTS(SELECT 1 FROM booking_accounting_review_tasks t WHERE t.id=NEW.task_id AND t.tenant_id=NEW.tenant_id AND t.qbo_realm_snapshot IS NOT NULL AND t.qbo_realm_snapshot=NEW.external_company_reference) THEN RAISE EXCEPTION 'external accounting company mapping required'; END IF;
      IF NOT NEW.receipt_liability_recorded THEN RAISE EXCEPTION 'receipt liability acknowledgment required'; END IF;
      IF EXISTS(SELECT 1 FROM booking_accounting_review_tasks t WHERE t.id=NEW.task_id AND t.tenant_id=NEW.tenant_id AND t.object_kind='booking_receipt_application') AND (NOT NEW.application_to_ar_recorded OR NOT EXISTS(SELECT 1 FROM booking_accounting_review_tasks t JOIN booking_accounting_review_tasks liability ON liability.receipt_id=t.receipt_id AND liability.tenant_id=t.tenant_id AND liability.object_kind='booking_receipt_liability' WHERE t.id=NEW.task_id AND t.tenant_id=NEW.tenant_id AND liability.state='externally_reconciled')) THEN RAISE EXCEPTION 'prior liability and application acknowledgment required'; END IF;
      RETURN NEW;
    END $$""")
    op.execute('CREATE TRIGGER booking_accounting_ack_actor BEFORE INSERT ON booking_accounting_review_events FOR EACH ROW EXECUTE FUNCTION guard_booking_accounting_ack()')
    op.execute("""CREATE FUNCTION guard_booking_task_ack_evidence() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
      IF NEW.state='externally_reconciled' AND NOT EXISTS(SELECT 1 FROM booking_accounting_review_events e WHERE e.task_id=NEW.id AND e.tenant_id=NEW.tenant_id AND e.after_state='externally_reconciled') THEN RAISE EXCEPTION 'accounting task acknowledgment lacks evidence'; END IF;
      RETURN NEW; END $$""")
    op.execute('CREATE CONSTRAINT TRIGGER booking_task_ack_evidence AFTER INSERT OR UPDATE ON booking_accounting_review_tasks DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION guard_booking_task_ack_evidence()')
    # A provider refund cannot dispose of already applied liability.
    op.execute("""CREATE FUNCTION guard_booking_applied_refund() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE used bigint;
    BEGIN
      SELECT COALESCE(SUM(amount_minor),0) INTO used FROM booking_receipt_applications WHERE receipt_id=NEW.id AND tenant_id=NEW.tenant_id;
      IF NEW.refunded_amount_minor+used>NEW.amount_received_minor AND NOT EXISTS(
        SELECT 1 FROM booking_payment_events e WHERE e.tenant_id=NEW.tenant_id AND e.appointment_id=NEW.appointment_id AND e.attempt_id=NEW.attempt_id
          AND e.provider=NEW.provider AND e.provider_account_id=NEW.provider_account_id
          AND e.source IN ('server_retrieval','verified_connect_webhook') AND length(e.proof_sha256)=64
          AND e.verified_refund_amount_minor=NEW.refunded_amount_minor AND e.verified_refund_amount_minor>0
      ) THEN RAISE EXCEPTION 'booking refund exceeds unapplied liability without verified source fact'; END IF;
      IF (NEW.refunded_amount_minor IS DISTINCT FROM OLD.refunded_amount_minor) AND NEW.version<>OLD.version+1 THEN RAISE EXCEPTION 'booking refund requires new receipt version'; END IF;
      RETURN NEW;
    END $$""")
    op.execute('CREATE TRIGGER booking_applied_refund_guard BEFORE UPDATE ON booking_receipts FOR EACH ROW EXECUTE FUNCTION guard_booking_applied_refund()')
    op.execute("""CREATE OR REPLACE FUNCTION guard_booking_confirmation() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
      IF TG_OP='UPDATE' AND OLD.booking_payment_version=1 AND OLD.status IN ('confirmed','in_progress','completed')
        AND NEW.status=OLD.status AND NEW.confirmed_receipt_id=OLD.confirmed_receipt_id
        AND NEW.booking_payment_state IN ('refund_pending','refunded') AND EXISTS(
          SELECT 1 FROM booking_receipts r JOIN booking_payment_events e ON e.tenant_id=r.tenant_id AND e.appointment_id=r.appointment_id AND e.attempt_id=r.attempt_id
          WHERE r.id=NEW.confirmed_receipt_id AND r.tenant_id=NEW.tenant_id AND r.appointment_id=NEW.id
            AND e.provider=r.provider AND e.provider_account_id=r.provider_account_id
            AND e.source IN ('server_retrieval','verified_connect_webhook') AND length(e.proof_sha256)=64
            AND e.verified_refund_amount_minor>0 AND e.verified_refund_amount_minor<=r.amount_received_minor
            AND e.after_state=NEW.booking_payment_state
            AND ((NEW.booking_payment_state='refunded' AND e.verified_refund_amount_minor=r.amount_received_minor)
              OR (NEW.booking_payment_state='refund_pending' AND e.verified_refund_amount_minor<r.amount_received_minor))
        ) THEN RETURN NEW; END IF;
      IF TG_OP='UPDATE' AND OLD.booking_payment_version=1 AND OLD.status IN ('confirmed','in_progress','completed')
        AND NEW.status=OLD.status AND NEW.confirmed_receipt_id=OLD.confirmed_receipt_id
        AND NEW.booking_payment_state='payment_received_review' AND EXISTS(
          SELECT 1 FROM booking_receipts r JOIN booking_payment_events e ON e.tenant_id=r.tenant_id AND e.appointment_id=r.appointment_id AND e.attempt_id=r.attempt_id
          WHERE r.id=NEW.confirmed_receipt_id AND r.tenant_id=NEW.tenant_id AND r.appointment_id=NEW.id
            AND e.provider=r.provider AND e.provider_account_id=r.provider_account_id
            AND e.source IN ('server_retrieval','verified_connect_webhook') AND length(e.proof_sha256)=64
            AND e.verified_dispute_amount_minor>0 AND e.verified_dispute_amount_minor<=r.amount_received_minor
            AND e.after_state='payment_received_review'
        ) THEN RETURN NEW; END IF;
      IF NEW.booking_payment_version=1 AND NEW.status IN ('confirmed','in_progress','completed') AND (NEW.booking_payment_state<>'paid' OR NEW.confirmed_receipt_id IS NULL OR NOT EXISTS(SELECT 1 FROM booking_receipts r WHERE r.id=NEW.confirmed_receipt_id AND r.tenant_id=NEW.tenant_id AND r.appointment_id=NEW.id AND r.currency='usd' AND r.amount_received_minor-r.refunded_amount_minor=NEW.price*100 AND r.verification_basis IN ('server_retrieval','verified_connect_webhook'))) THEN RAISE EXCEPTION 'verified full booking receipt required'; END IF;
      RETURN NEW; END; $$""")



def downgrade():
    raise RuntimeError('Booking prepayment applications and accounting evidence must not be deleted by downgrade')
