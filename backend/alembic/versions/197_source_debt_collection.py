"""One source debt, native collection lineage and append-only receipt acknowledgements."""
from alembic import op
import sqlalchemy as sa
revision = "197_source_debt_collection"
down_revision = "196_historical_owner_self_review"
branch_labels = None
depends_on = None

def upgrade():
    op.execute('ALTER TABLE invoices ADD COLUMN source_debt_handoff_id UUID')
    op.execute('ALTER TABLE invoices ADD CONSTRAINT uq_invoices_tenant_id UNIQUE (tenant_id,id)')
    op.execute('ALTER TABLE invoices ADD CONSTRAINT uq_invoice_source_handoff UNIQUE (tenant_id,source_debt_handoff_id)')
    op.execute('ALTER TABLE invoices DROP CONSTRAINT ck_invoice_accounting_policy')
    op.execute("ALTER TABLE invoices ADD CONSTRAINT ck_invoice_accounting_policy CHECK (accounting_policy IN ('standard','local_cash_only','historical_export_hold','source_collection_hold'))")
    op.execute('DROP INDEX ux_invoices_active_repair_order_id')
    op.execute("CREATE UNIQUE INDEX ux_invoices_active_repair_order_id ON invoices(repair_order_id) WHERE status <> 'cancelled' AND accounting_policy <> 'source_collection_hold'")
    op.execute("CREATE TABLE source_debt_handoffs (\n\ttenant_id UUID NOT NULL, \n\tsource_kind VARCHAR(32) NOT NULL, \n\tets_shop_id VARCHAR(160) NOT NULL, \n\tets_service_internal_id VARCHAR(160) NOT NULL, \n\tets_invoice_internal_id VARCHAR(160) NOT NULL, \n\tsource_invoice_number VARCHAR(80) NOT NULL, \n\tsource_service_number VARCHAR(80) NOT NULL, \n\tsource_dbn_invoice_id UUID NOT NULL, \n\tsource_repair_order_id UUID NOT NULL, \n\tcustomer_id UUID NOT NULL, \n\tsource_customer_id UUID NOT NULL, \n\tbill_to_authorization JSONB NOT NULL, \n\tbill_to_authorization_canonical TEXT NOT NULL, \n\tbill_to_authorization_sha256 VARCHAR(64) NOT NULL, \n\tnative_invoice_id UUID, \n\tsource_capture_document JSONB NOT NULL, \n\tsource_capture_sha256 VARCHAR(64) NOT NULL, \n\tsource_observed_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\toriginal_issued_total NUMERIC(12, 2) NOT NULL, \n\tsource_prior_allocated NUMERIC(12, 2) NOT NULL, \n\topening_principal NUMERIC(12, 2) NOT NULL, \n\tcurrency VARCHAR(3) NOT NULL, \n\tstate VARCHAR(32) NOT NULL, \n\tsource_revision VARCHAR(64) NOT NULL, \n\tversion INTEGER NOT NULL, \n\towner_acknowledged_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\towner_acknowledged_by UUID NOT NULL, \n\taccounting_state VARCHAR(48) NOT NULL, \n\taccounting_owner VARCHAR(32) NOT NULL, \n\tidempotency_key VARCHAR(255) NOT NULL, \n\trequest_sha256 VARCHAR(64) NOT NULL, \n\tid UUID NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tdeleted_at TIMESTAMP WITH TIME ZONE, \n\tPRIMARY KEY (id), \n\tCONSTRAINT uq_source_handoff_tenant_id UNIQUE (tenant_id, id), \n\tCONSTRAINT uq_source_handoff_debt UNIQUE (tenant_id, ets_shop_id, ets_invoice_internal_id), \n\tCONSTRAINT uq_source_handoff_idempotency UNIQUE (tenant_id, idempotency_key), \n\tCONSTRAINT fk_source_handoff_order FOREIGN KEY(tenant_id, source_repair_order_id) REFERENCES repair_orders (tenant_id, id), \n\tCONSTRAINT fk_source_handoff_source_customer FOREIGN KEY(tenant_id, source_customer_id) REFERENCES customers (tenant_id, id), \n\tCONSTRAINT fk_source_handoff_customer FOREIGN KEY(tenant_id, customer_id) REFERENCES customers (tenant_id, id), \n\tCONSTRAINT ck_source_handoff_identity CHECK (currency='USD' AND source_kind='easy_truck_shop'), \n\tCONSTRAINT ck_source_handoff_state CHECK (state IN ('prepared','active','source_conflict','closed') AND version>=1), \n\tCONSTRAINT ck_source_handoff_money CHECK (opening_principal>0 AND source_prior_allocated>=0 AND original_issued_total=source_prior_allocated+opening_principal), \n\tCONSTRAINT ck_source_handoff_accounting CHECK (accounting_owner='external_manual' AND accounting_state IN ('external_reconciliation_pending','verified_external')), \n\tFOREIGN KEY(tenant_id) REFERENCES tenants (id), \n\tUNIQUE (native_invoice_id), \n\tFOREIGN KEY(owner_acknowledged_by) REFERENCES users (id)\n)")
    op.execute("CREATE TABLE ets_receipt_update_tasks (\n\ttenant_id UUID NOT NULL, \n\thandoff_id UUID NOT NULL, \n\tinvoice_id UUID NOT NULL, \n\tpayment_id UUID NOT NULL, \n\tattempt_id UUID, \n\tprincipal_amount NUMERIC(12, 2) NOT NULL, \n\treceived_amount NUMERIC(12, 2) NOT NULL, \n\tfee_amount NUMERIC(12, 2) NOT NULL, \n\tunapplied_amount NUMERIC(12, 2) NOT NULL, \n\tcurrency VARCHAR(3) NOT NULL, \n\teffective_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\texpected_source_revision VARCHAR(64) NOT NULL, \n\tstate VARCHAR(32) NOT NULL, \n\tversion INTEGER NOT NULL, \n\tclaimed_by UUID, \n\tclaim_expires_at TIMESTAMP WITH TIME ZONE, \n\tverified_at TIMESTAMP WITH TIME ZONE, \n\tid UUID NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tdeleted_at TIMESTAMP WITH TIME ZONE, \n\tPRIMARY KEY (id), \n\tCONSTRAINT uq_ets_task_tenant_id UNIQUE (tenant_id, id), \n\tCONSTRAINT uq_ets_task_payment UNIQUE (tenant_id, payment_id), \n\tCONSTRAINT fk_ets_task_handoff FOREIGN KEY(tenant_id, handoff_id) REFERENCES source_debt_handoffs (tenant_id, id), \n\tCONSTRAINT fk_ets_task_invoice FOREIGN KEY(tenant_id, invoice_id) REFERENCES invoices (tenant_id, id), \n\tCONSTRAINT ck_ets_task_state CHECK (state IN ('pending_manual','claimed','awaiting_verification','verified','conflict') AND version>=1), \n\tCONSTRAINT ck_ets_task_money CHECK (currency='USD' AND principal_amount>0 AND received_amount>=principal_amount AND fee_amount>=0 AND unapplied_amount>=0), \n\tFOREIGN KEY(payment_id) REFERENCES payments (id), \n\tFOREIGN KEY(attempt_id) REFERENCES invoice_payment_attempts (id), \n\tFOREIGN KEY(claimed_by) REFERENCES users (id)\n)")
    op.execute("CREATE TABLE source_receipt_links (\n\ttenant_id UUID NOT NULL, \n\thandoff_id UUID NOT NULL, \n\tets_shop_id VARCHAR(160) NOT NULL, \n\tets_invoice_internal_id VARCHAR(160) NOT NULL, \n\tsource_allocation_id VARCHAR(160) NOT NULL, \n\tsource_payment_id VARCHAR(160) NOT NULL, \n\tsource_revision VARCHAR(64) NOT NULL, \n\tsource_capture_sha256 VARCHAR(64) NOT NULL, \n\tcontent_sha256 VARCHAR(64) NOT NULL, \n\tamount NUMERIC(12, 2) NOT NULL, \n\teffective_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\torigin VARCHAR(24) NOT NULL, \n\tnative_payment_id UUID, \n\ttask_id UUID, \n\treverses_id UUID, \n\tid UUID NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tdeleted_at TIMESTAMP WITH TIME ZONE, \n\tPRIMARY KEY (id), \n\tCONSTRAINT uq_source_receipt_allocation UNIQUE (tenant_id, ets_shop_id, ets_invoice_internal_id, source_allocation_id), \n\tCONSTRAINT fk_source_receipt_handoff FOREIGN KEY(tenant_id, handoff_id) REFERENCES source_debt_handoffs (tenant_id, id), \n\tCONSTRAINT fk_source_receipt_task FOREIGN KEY(tenant_id, task_id) REFERENCES ets_receipt_update_tasks (tenant_id, id), \n\tCONSTRAINT ck_source_receipt_amount CHECK (amount>0 AND origin IN ('dbn_ack','ets_external')), \n\tFOREIGN KEY(native_payment_id) REFERENCES payments (id), \n\tFOREIGN KEY(reverses_id) REFERENCES source_receipt_links (id)\n)")
    op.execute('CREATE TABLE source_debt_events (\n\ttenant_id UUID NOT NULL, \n\thandoff_id UUID NOT NULL, \n\ttask_id UUID, \n\tactor_user_id UUID, \n\tevent_type VARCHAR(48) NOT NULL, \n\trequest_key VARCHAR(255) NOT NULL, \n\trequest_sha256 VARCHAR(64) NOT NULL, \n\tversion INTEGER NOT NULL, \n\tevidence JSONB NOT NULL, \n\tid UUID NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tdeleted_at TIMESTAMP WITH TIME ZONE, \n\tPRIMARY KEY (id), \n\tCONSTRAINT uq_source_debt_event_request UNIQUE (tenant_id, request_key), \n\tCONSTRAINT fk_source_debt_event_handoff FOREIGN KEY(tenant_id, handoff_id) REFERENCES source_debt_handoffs (tenant_id, id), \n\tCONSTRAINT fk_source_debt_event_task FOREIGN KEY(tenant_id, task_id) REFERENCES ets_receipt_update_tasks (tenant_id, id), \n\tCONSTRAINT ck_source_debt_event_version CHECK (version>=1), \n\tFOREIGN KEY(actor_user_id) REFERENCES users (id)\n)')
    op.execute('ALTER TABLE source_debt_handoffs ADD CONSTRAINT fk_source_handoff_native FOREIGN KEY(tenant_id, native_invoice_id) REFERENCES invoices (tenant_id, id)')
    op.execute('ALTER TABLE source_debt_handoffs ADD CONSTRAINT fk_source_handoff_invoice FOREIGN KEY(tenant_id, source_dbn_invoice_id) REFERENCES invoices (tenant_id, id)')
    op.execute('ALTER TABLE invoices ADD CONSTRAINT fk_invoice_source_handoff FOREIGN KEY(tenant_id, source_debt_handoff_id) REFERENCES source_debt_handoffs (tenant_id, id)')
    op.execute("ALTER TABLE invoices ADD CONSTRAINT ck_invoice_collection_lineage CHECK ((accounting_policy = 'source_collection_hold') = (source_debt_handoff_id IS NOT NULL) AND (source_debt_handoff_id IS NULL OR (source IS NOT NULL AND source = 'ets_collection_handoff')) AND (source IS NULL OR source <> 'ets_collection_handoff' OR source_debt_handoff_id IS NOT NULL))")
    op.execute("CREATE FUNCTION reject_source_debt_evidence_mutation() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'source collection evidence is append-only'; END; $$")
    op.execute('CREATE TRIGGER immutable_source_receipt_links BEFORE UPDATE OR DELETE ON source_receipt_links FOR EACH ROW EXECUTE FUNCTION reject_source_debt_evidence_mutation()')
    op.execute('CREATE TRIGGER immutable_source_debt_events BEFORE UPDATE OR DELETE ON source_debt_events FOR EACH ROW EXECUTE FUNCTION reject_source_debt_evidence_mutation()')
    op.execute("CREATE FUNCTION guard_source_handoff_snapshot() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN\n IF TG_OP='DELETE' THEN RAISE EXCEPTION 'source debt history cannot be deleted'; END IF;\n IF (to_jsonb(OLD)-ARRAY['updated_at','native_invoice_id','state','version','accounting_state','source_revision','source_observed_at']) IS DISTINCT FROM (to_jsonb(NEW)-ARRAY['updated_at','native_invoice_id','state','version','accounting_state','source_revision','source_observed_at']) THEN RAISE EXCEPTION 'source debt opening snapshot is immutable'; END IF;\n IF NEW.version<OLD.version THEN RAISE EXCEPTION 'source debt version cannot decrease'; END IF;\n RETURN NEW; END; $$")
    op.execute('CREATE TRIGGER immutable_source_handoff_snapshot BEFORE UPDATE OR DELETE ON source_debt_handoffs FOR EACH ROW EXECUTE FUNCTION guard_source_handoff_snapshot()')


    op.execute("""CREATE FUNCTION guard_source_collection_bindings() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE h source_debt_handoffs; p payments; a invoice_payment_attempts;
    BEGIN
      SELECT * INTO h FROM source_debt_handoffs WHERE id=NEW.handoff_id AND tenant_id=NEW.tenant_id;
      IF h.id IS NULL THEN RAISE EXCEPTION 'source collection tenant binding mismatch'; END IF;
      IF TG_TABLE_NAME='ets_receipt_update_tasks' THEN
        SELECT * INTO p FROM payments WHERE id=NEW.payment_id AND tenant_id=NEW.tenant_id AND invoice_id=h.native_invoice_id;
        IF NEW.invoice_id IS DISTINCT FROM h.native_invoice_id OR p.id IS NULL THEN RAISE EXCEPTION 'source collection receipt binding mismatch'; END IF;
        IF NEW.attempt_id IS NOT NULL THEN
          SELECT * INTO a FROM invoice_payment_attempts WHERE id=NEW.attempt_id AND tenant_id=NEW.tenant_id AND invoice_id=h.native_invoice_id;
          IF a.id IS NULL OR p.invoice_payment_attempt_id IS DISTINCT FROM a.id THEN RAISE EXCEPTION 'source collection attempt binding mismatch'; END IF;
        END IF;
      ELSE
        IF NEW.ets_shop_id IS DISTINCT FROM h.ets_shop_id OR NEW.ets_invoice_internal_id IS DISTINCT FROM h.ets_invoice_internal_id THEN RAISE EXCEPTION 'source receipt debt binding mismatch'; END IF;
        SELECT * INTO p FROM payments WHERE id=NEW.native_payment_id AND tenant_id=NEW.tenant_id AND invoice_id=h.native_invoice_id;
        IF p.id IS NULL THEN RAISE EXCEPTION 'source receipt payment binding mismatch'; END IF;
        IF NEW.origin='dbn_ack' AND NOT EXISTS(SELECT 1 FROM ets_receipt_update_tasks t WHERE t.id=NEW.task_id AND t.tenant_id=NEW.tenant_id AND t.handoff_id=h.id AND t.payment_id=NEW.native_payment_id) THEN RAISE EXCEPTION 'source receipt task binding mismatch'; END IF;
        IF NEW.origin='ets_external' AND NEW.task_id IS NOT NULL THEN RAISE EXCEPTION 'external receipt cannot acknowledge a DBN task'; END IF;
      END IF;
      RETURN NEW;
    END; $$""")
    op.execute('CREATE TRIGGER check_ets_task_binding BEFORE INSERT OR UPDATE ON ets_receipt_update_tasks FOR EACH ROW EXECUTE FUNCTION guard_source_collection_bindings()')
    op.execute('CREATE TRIGGER check_source_receipt_binding BEFORE INSERT ON source_receipt_links FOR EACH ROW EXECUTE FUNCTION guard_source_collection_bindings()')
    op.execute("""CREATE FUNCTION guard_source_collection_invoice() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE h source_debt_handoffs;
    BEGIN
      IF TG_OP='UPDATE' AND OLD.accounting_policy='source_collection_hold' AND
        ROW(NEW.accounting_policy,NEW.source,NEW.source_debt_handoff_id,NEW.tenant_id,NEW.repair_order_id,NEW.billed_customer_id)
        IS DISTINCT FROM ROW(OLD.accounting_policy,OLD.source,OLD.source_debt_handoff_id,OLD.tenant_id,OLD.repair_order_id,OLD.billed_customer_id)
        THEN RAISE EXCEPTION 'source collection lineage is immutable'; END IF;
      IF NEW.accounting_policy='source_collection_hold' THEN
        SELECT * INTO h FROM source_debt_handoffs WHERE id=NEW.source_debt_handoff_id AND tenant_id=NEW.tenant_id;
        IF h.id IS NULL OR NEW.repair_order_id IS DISTINCT FROM h.source_repair_order_id OR NEW.billed_customer_id IS DISTINCT FROM h.customer_id OR NEW.total_amount IS DISTINCT FROM h.opening_principal OR NEW.subtotal IS DISTINCT FROM h.opening_principal OR NEW.tax_amount<>0 OR NEW.service_fee_amount<>0 OR NEW.shop_supplies_amount<>0 OR NEW.discount_amount<>0 THEN RAISE EXCEPTION 'source collection document binding mismatch'; END IF;
        IF h.native_invoice_id IS NOT NULL AND h.native_invoice_id<>NEW.id THEN RAISE EXCEPTION 'source debt already has a native document'; END IF;
      END IF;
      RETURN NEW;
    END; $$""")
    op.execute('CREATE TRIGGER check_source_collection_invoice BEFORE INSERT OR UPDATE ON invoices FOR EACH ROW EXECUTE FUNCTION guard_source_collection_invoice()')
    op.execute("""CREATE FUNCTION guard_handoff_native_binding() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
      IF OLD.native_invoice_id IS NOT NULL AND NEW.native_invoice_id IS DISTINCT FROM OLD.native_invoice_id THEN RAISE EXCEPTION 'native collection identity is immutable'; END IF;
      IF NEW.native_invoice_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM invoices i WHERE i.id=NEW.native_invoice_id AND i.tenant_id=NEW.tenant_id AND i.source_debt_handoff_id=NEW.id AND i.accounting_policy='source_collection_hold') THEN RAISE EXCEPTION 'native collection lineage mismatch'; END IF;
      RETURN NEW; END; $$""")
    op.execute('CREATE TRIGGER check_handoff_native_binding BEFORE UPDATE ON source_debt_handoffs FOR EACH ROW EXECUTE FUNCTION guard_handoff_native_binding()')


    op.execute("""CREATE FUNCTION guard_handed_off_source_money() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE owner_tenant UUID; source_invoice UUID; linked BOOLEAN;
    BEGIN
      IF TG_OP='UPDATE' THEN
        PERFORM pg_advisory_xact_lock(('x'||substr(encode(sha256(convert_to('dieselbridge:financial:v1:'||OLD.tenant_id::text,'UTF8')),'hex'),1,16))::bit(64)::bigint);
        IF TG_TABLE_NAME='payments' THEN
          IF EXISTS(SELECT 1 FROM source_debt_handoffs WHERE tenant_id=OLD.tenant_id AND source_dbn_invoice_id=OLD.invoice_id) THEN RAISE EXCEPTION 'handed-off source payment is read-only'; END IF;
        ELSIF NEW.tenant_id IS DISTINCT FROM OLD.tenant_id AND EXISTS(SELECT 1 FROM source_debt_handoffs WHERE tenant_id=OLD.tenant_id AND source_dbn_invoice_id=OLD.id) THEN RAISE EXCEPTION 'handed-off source tenant is immutable'; END IF;
      END IF;
      IF TG_OP='DELETE' THEN owner_tenant=OLD.tenant_id; ELSE owner_tenant=NEW.tenant_id; END IF;
      PERFORM pg_advisory_xact_lock(('x'||substr(encode(sha256(convert_to('dieselbridge:financial:v1:'||owner_tenant::text,'UTF8')),'hex'),1,16))::bit(64)::bigint);
      IF TG_TABLE_NAME='invoices' THEN
        IF TG_OP='INSERT' THEN RETURN NEW; END IF;
        source_invoice=OLD.id;
      ELSE
        IF TG_OP='DELETE' THEN source_invoice=OLD.invoice_id; ELSE source_invoice=NEW.invoice_id; END IF;
      END IF;
      SELECT EXISTS(SELECT 1 FROM source_debt_handoffs WHERE tenant_id=owner_tenant AND source_dbn_invoice_id=source_invoice) INTO linked;
      IF linked THEN
        IF TG_TABLE_NAME='payments' OR TG_OP='DELETE' THEN RAISE EXCEPTION 'handed-off source financial history is read-only'; END IF;
        IF (to_jsonb(OLD)-ARRAY['updated_at','ets_source_evidence']) IS DISTINCT FROM (to_jsonb(NEW)-ARRAY['updated_at','ets_source_evidence']) THEN RAISE EXCEPTION 'handed-off source financial history is read-only'; END IF;
      END IF;
      IF TG_OP='DELETE' THEN RETURN OLD; END IF; RETURN NEW;
    END; $$""")
    op.execute('CREATE TRIGGER freeze_handed_off_invoice BEFORE UPDATE OR DELETE ON invoices FOR EACH ROW EXECUTE FUNCTION guard_handed_off_source_money()')
    op.execute('CREATE TRIGGER freeze_handed_off_payment BEFORE INSERT OR UPDATE OR DELETE ON payments FOR EACH ROW EXECUTE FUNCTION guard_handed_off_source_money()')


    op.execute("""CREATE FUNCTION db149_collection_bill_to_matches(invoice_uuid UUID, tenant_uuid UUID, customer_uuid UUID, order_uuid UUID)
    RETURNS BOOLEAN LANGUAGE SQL STABLE AS $$
      SELECT EXISTS(
        SELECT 1 FROM invoices i
        JOIN source_debt_handoffs h ON h.id=i.source_debt_handoff_id AND h.native_invoice_id=i.id AND h.tenant_id=i.tenant_id
        JOIN repair_orders ro ON ro.id=h.source_repair_order_id AND ro.tenant_id=h.tenant_id
        JOIN invoices original ON original.id=h.source_dbn_invoice_id AND original.tenant_id=h.tenant_id AND original.repair_order_id=ro.id
        JOIN customers source_customer ON source_customer.id=h.source_customer_id AND source_customer.tenant_id=h.tenant_id AND source_customer.deleted_at IS NULL
        JOIN customers target_customer ON target_customer.id=h.customer_id AND target_customer.tenant_id=h.tenant_id AND target_customer.deleted_at IS NULL
        WHERE i.id=invoice_uuid AND i.tenant_id=tenant_uuid AND i.repair_order_id=order_uuid
          AND i.accounting_policy='source_collection_hold' AND i.source='ets_collection_handoff'
          AND i.billed_customer_id=customer_uuid AND h.customer_id=customer_uuid AND ro.id=order_uuid
          AND ro.customer_id=h.source_customer_id AND COALESCE(original.billed_customer_id,ro.customer_id)=h.source_customer_id
          AND original.source='easy_truck_shop_import' AND ro.source='easy_truck_shop_import'
          AND original.deleted_at IS NULL AND original.voided_at IS NULL AND original.status<>'cancelled'
          AND ro.status<>'cancelled' AND NOT source_customer.is_internal_fleet AND NOT target_customer.is_internal_fleet
          AND NOT original.is_internal AND NOT ro.is_internal AND NOT i.is_internal
          AND h.bill_to_authorization_canonical::jsonb=h.bill_to_authorization
          AND encode(sha256(convert_to(h.bill_to_authorization_canonical,'UTF8')),'hex')=h.bill_to_authorization_sha256
          AND h.bill_to_authorization->>'schema_version'='1'
          AND h.bill_to_authorization->>'source_capture_sha256'=h.source_capture_sha256
          AND h.bill_to_authorization->>'tenant_id'=h.tenant_id::text
          AND h.bill_to_authorization->>'source_invoice_id'=h.source_dbn_invoice_id::text
          AND h.bill_to_authorization->>'source_customer_id'=h.source_customer_id::text
          AND h.bill_to_authorization->>'target_customer_id'=h.customer_id::text
          AND h.bill_to_authorization->>'ets_shop_id'=h.ets_shop_id
          AND h.bill_to_authorization->>'ets_invoice_internal_id'=h.ets_invoice_internal_id
          AND h.bill_to_authorization->>'actor_user_id'=h.owner_acknowledged_by::text
          AND ((h.source_customer_id=h.customer_id AND h.bill_to_authorization->>'mode'='same_customer')
            OR (h.source_customer_id<>h.customer_id AND h.bill_to_authorization->>'mode'='owner_same_legal_entity'
              AND h.bill_to_authorization->>'attested_same_legal_entity'='true'))
      );
    $$""")
    # Extend only the settlement branch. Credit, attempt, ledger, overpayment,
    # refund and all other pre-existing identity guards retain their exact SQL.
    definition = op.get_bind().scalar(sa.text("SELECT pg_get_functiondef('enforce_db048_tenant_integrity()'::regprocedure)"))
    old_guard = 'AND ro.customer_id = NEW.customer_id'
    if definition.count(old_guard) != 2:
        raise RuntimeError('Unexpected DB-048 integrity definition; review before extending collection bill-to')
    replacement = "AND ((i.accounting_policy <> 'source_collection_hold' AND ro.customer_id = NEW.customer_id) OR db149_collection_bill_to_matches(i.id,NEW.tenant_id,NEW.customer_id,ro.id))"
    op.execute(sa.text(definition.replace(old_guard,replacement,1)))


def downgrade():
    if op.get_bind().scalar(sa.text('SELECT EXISTS(SELECT 1 FROM source_debt_handoffs)')):
        raise RuntimeError('Source debt history exists; use reviewed forward remediation instead of dropping evidence')
    definition = op.get_bind().scalar(sa.text("SELECT pg_get_functiondef('enforce_db048_tenant_integrity()'::regprocedure)"))
    replacement = "AND ((i.accounting_policy <> 'source_collection_hold' AND ro.customer_id = NEW.customer_id) OR db149_collection_bill_to_matches(i.id,NEW.tenant_id,NEW.customer_id,ro.id))"
    if definition.count(replacement) != 1:raise RuntimeError('Unexpected collection integrity definition')
    op.execute(sa.text(definition.replace(replacement,'AND ro.customer_id = NEW.customer_id',1)))
    op.execute('DROP FUNCTION db149_collection_bill_to_matches(UUID,UUID,UUID,UUID)')
    op.execute('DROP TRIGGER freeze_handed_off_invoice ON invoices')
    op.execute('DROP TRIGGER freeze_handed_off_payment ON payments')
    op.execute('DROP FUNCTION guard_handed_off_source_money()')
    op.execute('DROP TRIGGER check_source_collection_invoice ON invoices')
    op.execute('DROP FUNCTION guard_source_collection_invoice()')
    op.execute('DROP TRIGGER check_handoff_native_binding ON source_debt_handoffs')
    op.execute('DROP FUNCTION guard_handoff_native_binding()')
    op.execute('DROP TRIGGER check_ets_task_binding ON ets_receipt_update_tasks')
    op.execute('DROP TRIGGER check_source_receipt_binding ON source_receipt_links')
    op.execute('DROP FUNCTION guard_source_collection_bindings()')
    op.execute('ALTER TABLE invoices DROP CONSTRAINT ck_invoice_collection_lineage')
    op.execute('ALTER TABLE invoices DROP CONSTRAINT fk_invoice_source_handoff')
    for table in ('source_debt_events','source_receipt_links','ets_receipt_update_tasks','source_debt_handoffs'):
        op.drop_table(table)
    op.execute('DROP FUNCTION guard_source_handoff_snapshot()')
    op.execute('DROP FUNCTION reject_source_debt_evidence_mutation()')
    op.execute('ALTER TABLE invoices DROP CONSTRAINT uq_invoice_source_handoff')
    op.execute('ALTER TABLE invoices DROP CONSTRAINT uq_invoices_tenant_id')
    op.drop_column('invoices','source_debt_handoff_id')
    op.execute('ALTER TABLE invoices DROP CONSTRAINT ck_invoice_accounting_policy')
    op.execute("ALTER TABLE invoices ADD CONSTRAINT ck_invoice_accounting_policy CHECK (accounting_policy IN ('standard','local_cash_only','historical_export_hold'))")
    op.drop_index('ux_invoices_active_repair_order_id',table_name='invoices')
    op.execute("CREATE UNIQUE INDEX ux_invoices_active_repair_order_id ON invoices(repair_order_id) WHERE status <> 'cancelled'")
