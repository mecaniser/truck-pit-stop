"""Opt-in disposable PG tests: actual locks, SQL fences and evidence rollback."""
import os
from datetime import datetime,timezone,timedelta
from types import SimpleNamespace
from uuid import uuid4
import pytest
import psycopg2
import psycopg2.extras
from psycopg2 import sql
from scripts.easytruck_sync import import_to_truckpitstop as importer
from scripts.easytruck_sync import persist_invoice_evidence as ops
from scripts.easytruck_sync.source_evidence import normalize_source_evidence,append_source_evidence

pytestmark=pytest.mark.skipif(not os.environ.get('DB149_TEST_DATABASE_URL'),reason='Explicit disposable PG fixture required')

@pytest.fixture
def pg():
    url=os.environ['DB149_TEST_DATABASE_URL'].replace('postgresql+asyncpg://','postgresql://',1)
    psycopg2.extras.register_uuid()
    schema='db149_ingest_'+uuid4().hex
    admin=psycopg2.connect(url);admin.autocommit=True
    with admin.cursor() as c:c.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
    connections=[]
    def connect():
        c=psycopg2.connect(url);connections.append(c)
        with c.cursor() as cursor:cursor.execute(sql.SQL('SET search_path TO {},public').format(sql.Identifier(schema)))
        c.commit();return c
    conn=connect()
    with conn.cursor() as c:
        c.execute('CREATE TABLE invoices(id uuid PRIMARY KEY,tenant_id uuid,repair_order_id uuid,invoice_number text,source text,status text,total_amount numeric,paid_at timestamptz,deleted_at timestamptz,ets_source_evidence jsonb)')
        c.execute('CREATE TABLE source_debt_handoffs(id uuid PRIMARY KEY,tenant_id uuid,source_dbn_invoice_id uuid,source_repair_order_id uuid,native_invoice_id uuid,ets_shop_id text,ets_service_internal_id text,ets_invoice_internal_id text,source_service_number text,source_invoice_number text,owner_acknowledged_at timestamptz,version integer,state text,deleted_at timestamptz)')
        for table,col in [('payments','invoice_id'),('invoice_settlements','invoice_id'),('invoice_payment_attempts','invoice_id'),('invoice_payment_ledger_events','invoice_id'),('payment_refunds','invoice_id'),('payment_overpayments','invoice_id'),('customer_credit_entries','target_invoice_id'),('payment_accounting_links','invoice_id'),('provider_outbox','aggregate_id'),('ets_receipt_update_tasks','invoice_id'),('source_receipt_links','handoff_id'),('source_debt_events','handoff_id')]:
            c.execute(sql.SQL('CREATE TABLE {}(id uuid PRIMARY KEY,tenant_id uuid,{} uuid,amount numeric)').format(sql.Identifier(table),sql.Identifier(col)))
    conn.commit()
    yield conn,connect
    for c in connections:c.close()
    with admin.cursor() as c:c.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))
    admin.close()


def seed(conn,state='prepared',deleted=False):
    tenant,invoice,order,handoff=[uuid4() for _ in range(4)]
    now=datetime.now(timezone.utc)
    facts={'schema_version':1,'source':'easy_truck_shop','ets_shop_id':'shop','service_id':'1821','service_internal_id':'506423','invoice_service_id':'506423','invoice_id':'468019','invoice_number':'1687','observed_at_source':(now-timedelta(minutes=10)).isoformat(),'payment_lines':[], 'invoice_manifest':{'complete':True,'evidence_kind':'verified_source_service_invoice_manifest','service_internal_id':'506423','invoice_ids':['468019']}}
    old=append_source_evidence(None,normalize_source_evidence(facts))
    with conn.cursor() as c:
        c.execute('INSERT INTO invoices VALUES(%s,%s,%s,%s,%s,%s,%s,NULL,NULL,%s)',(invoice,tenant,order,'ETSINV-1687','easy_truck_shop_import','sent','268.44',psycopg2.extras.Json(old)))
        c.execute('INSERT INTO source_debt_handoffs VALUES(%s,%s,%s,%s,NULL,%s,%s,%s,%s,%s,%s,1,%s,%s)',(handoff,tenant,invoice,order,'shop','506423','468019','1821','1687',now-timedelta(minutes=5),state,now if deleted else None))
        c.execute('INSERT INTO payments VALUES(%s,%s,%s,10)',(uuid4(),tenant,invoice))
    conn.commit()
    facts['observed_at_source']=(now-timedelta(minutes=1)).isoformat()
    doc={'schema_version':1,'capture_kind':'ets_target_invoice_evidence','tenant_id':str(tenant),'sourceEvidence':facts}
    args=SimpleNamespace(tenant_id=tenant,invoice_id=invoice,handoff_id=handoff,commit=True,expected_version=1,expected_envelope_sha256=ops.digest(old))
    return args,doc,old


@pytest.mark.parametrize('state',['prepared','active','source_conflict','closed'])
@pytest.mark.parametrize('deleted',[False,True])
def test_real_sql_creation_and_backfill_fence_all_permanent_states(pg,state,deleted):
    conn,_=pg;args,doc,_=seed(conn,state,deleted)
    stats={}
    with conn.cursor() as c:
        importer._create_invoice_and_payments(c,args.tenant_id,uuid4(),'ETS-1821-x','1821',{'1821':{'invoiceNumber':'1687','total':'268.44','sourceEvidence':doc['sourceEvidence']}},set(),stats,datetime.now())
        assert stats=={'source_debt_handoff_skipped':1}
        assert importer._source_debt_owned(c,args.tenant_id,'1821',None)
        assert not importer._source_debt_owned(c,uuid4(),'1821',{'invoiceNumber':'1687'})
        c.execute('SELECT count(*) FROM invoices');assert c.fetchone()[0]==1
    conn.rollback()


def test_real_financial_lock_prevents_prepare_import_race(pg):
    conn,connect=pg;args,doc,_=seed(conn);other=connect()
    with conn.cursor() as c:importer._lock_source_money(c,args.tenant_id)
    with other.cursor() as c:
        with pytest.raises(RuntimeError,match='busy'):importer._lock_source_money(c,args.tenant_id)
    other.rollback();conn.rollback()
    with other.cursor() as c:
        importer._lock_source_money(c,args.tenant_id)
        assert importer._source_debt_owned(c,args.tenant_id,'1821',{'invoiceNumber':'1687'})
    other.rollback()


def test_real_evidence_commit_preserves_financial_rows_and_version(pg):
    conn,_=pg;args,doc,old=seed(conn)
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as c:before=ops.fingerprint(c,args.tenant_id,[args.invoice_id])
    result=ops.persist(conn,args,doc);conn.commit()
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as c:
        assert ops.fingerprint(c,args.tenant_id,[args.invoice_id])==before
        c.execute('SELECT ets_source_evidence FROM invoices WHERE id=%s',(args.invoice_id,));assert c.fetchone()['ets_source_evidence']!=old
    assert result['financial_state_unchanged']


def test_real_dry_run_is_read_only_and_commit_rolls_back_financial_trigger_drift(pg):
    conn,_=pg;args,doc,old=seed(conn)
    args.commit=False
    conn.set_session(readonly=True)
    ops.persist(conn,args,doc);conn.rollback()
    conn.set_session(readonly=False)
    with conn.cursor() as c:
        c.execute('SELECT ets_source_evidence FROM invoices WHERE id=%s',(args.invoice_id,));assert c.fetchone()[0]==old
        c.execute("CREATE FUNCTION bad_projection() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN UPDATE payments SET amount=amount+1 WHERE invoice_id=NEW.id; RETURN NEW; END $$")
        c.execute('CREATE TRIGGER simulate_bad_projection AFTER UPDATE ON invoices FOR EACH ROW EXECUTE FUNCTION bad_projection()')
    conn.commit();args.commit=True
    with pytest.raises(ValueError,match='Financial state changed'):ops.persist(conn,args,doc)
    conn.rollback()
    with conn.cursor() as c:
        c.execute('SELECT amount FROM payments');assert str(c.fetchone()[0])=='10'
        c.execute('SELECT ets_source_evidence FROM invoices WHERE id=%s',(args.invoice_id,));assert c.fetchone()[0]==old


def test_real_cross_customer_legacy_holds_and_proven_drift_is_retained(pg):
    conn,_=pg;args,doc,old=seed(conn)
    with conn.cursor() as c:
        c.execute('ALTER TABLE source_debt_handoffs ADD COLUMN source_customer_id uuid, ADD COLUMN customer_id uuid, ADD COLUMN bill_to_authorization jsonb')
        c.execute('UPDATE source_debt_handoffs SET source_customer_id=%s,customer_id=%s,bill_to_authorization=%s',(uuid4(),uuid4(),psycopg2.extras.Json({'mode':'reviewed_same_legal_business','source_ets_customer_id':'97052'})))
    conn.commit()
    with pytest.raises(ValueError,match='requires captured source customer proof'):
        ops.persist(conn,args,doc)
    conn.rollback()
    doc['sourceEvidence'].update(source_customer_id='97053',source_customer_uuid='02104722-a300-48a5-ba98-0eab3b2fb32e',source_customer_deleted=False,source_customer_binding_kind='embedded_service_customer')
    result=ops.persist(conn,args,doc);conn.commit()
    assert result['financial_state_unchanged']
    with conn.cursor() as c:
        c.execute('SELECT ets_source_evidence FROM invoices WHERE id=%s',(args.invoice_id,))
        latest=ops.latest_source_evidence(c.fetchone()[0])
    assert latest['source_customer_id']=='97053'
    assert result['next_envelope_sha256']!=result['prior_envelope_sha256']


def bootstrap_fixture(conn):
    args,doc,old=seed(conn)
    customer=uuid4()
    with conn.cursor() as c:
        c.execute('SELECT source_repair_order_id FROM source_debt_handoffs WHERE id=%s',(args.handoff_id,));order=c.fetchone()[0]
        c.execute('DELETE FROM source_debt_handoffs WHERE id=%s',(args.handoff_id,))
        c.execute('ALTER TABLE invoices ADD COLUMN voided_at timestamptz, ADD COLUMN is_internal boolean DEFAULT false')
        c.execute('CREATE TABLE customers(id uuid PRIMARY KEY,tenant_id uuid,ets_external_id text,deleted_at timestamptz,is_internal_fleet boolean DEFAULT false)')
        c.execute("CREATE TABLE repair_orders(id uuid PRIMARY KEY,tenant_id uuid,customer_id uuid,source text,order_number text,deleted_at timestamptz,status text DEFAULT 'closed')")
        c.execute('INSERT INTO customers(id,tenant_id,ets_external_id,deleted_at) VALUES(%s,%s,%s,NULL)',(customer,args.tenant_id,'97052'))
        c.execute('INSERT INTO repair_orders(id,tenant_id,customer_id,source,order_number,deleted_at) VALUES(%s,%s,%s,%s,%s,NULL)',(order,args.tenant_id,customer,'easy_truck_shop_import','ETS-1821-97052'))
    conn.commit()
    bootstrap=SimpleNamespace(**vars(args));bootstrap.handoff_id=None;bootstrap.bootstrap=True
    bootstrap.source_customer_id=customer;bootstrap.expected_source_customer_id='97052'
    bootstrap.expected_source_customer_uuid='02104722-a300-48a5-ba98-0eab3b2fb32e'
    bootstrap.expected_version=None;bootstrap.expected_evidence_sha256=old['observations'][-1]['sha256']
    for key,value in dict(ets_shop_id='shop',source_service_number='1821',ets_service_internal_id='506423',ets_invoice_internal_id='468019',source_invoice_number='1687').items():setattr(bootstrap,key,value)
    doc['sourceEvidence'].update(source_customer_id='97052',source_customer_uuid=bootstrap.expected_source_customer_uuid,source_customer_deleted=False,source_customer_binding_kind='embedded_service_customer')
    return bootstrap,args,doc,old,order


def test_real_bootstrap_dry_run_then_prepare_fixture_then_postack_refresh(pg):
    conn,_=pg;b,prepared,doc,old,order=bootstrap_fixture(conn)
    b.commit=False;conn.set_session(readonly=True)
    assert ops.bootstrap(conn,b,doc)['mode']=='bootstrap-dry-run'
    conn.rollback();conn.set_session(readonly=False)
    with conn.cursor() as c:
        c.execute('SELECT ets_source_evidence FROM invoices WHERE id=%s',(b.invoice_id,));assert c.fetchone()[0]==old
    conn.rollback();b.commit=True
    assert ops.bootstrap(conn,b,doc)['financial_state_unchanged'];conn.commit()
    with conn.cursor() as c:
        c.execute('SELECT ets_source_evidence FROM invoices WHERE id=%s',(b.invoice_id,));updated=c.fetchone()[0]
        # Synthetic prepared fixture represents service handoff creation. Its
        # authority/activation acceptance belongs to the actual service PG gate.
        ack=datetime.now(timezone.utc)-timedelta(seconds=5)
        c.execute('INSERT INTO source_debt_handoffs VALUES(%s,%s,%s,%s,NULL,%s,%s,%s,%s,%s,%s,1,%s,NULL)',(prepared.handoff_id,b.tenant_id,b.invoice_id,order,'shop','506423','468019','1821','1687',ack,'prepared'))
    conn.commit();prepared.expected_envelope_sha256=ops.digest(updated)
    with pytest.raises(ValueError,match='Canonical handoff exists'):ops.bootstrap(conn,b,doc)
    conn.rollback()
    doc['sourceEvidence']['observed_at_source']=(datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat()
    assert ops.persist(conn,prepared,doc)['financial_state_unchanged'];conn.commit()
    with conn.cursor() as c:
        c.execute('SELECT amount FROM payments');assert str(c.fetchone()[0])=='10'
        c.execute('SELECT count(*) FROM invoices');assert c.fetchone()[0]==1
        c.execute('SELECT ets_source_evidence FROM invoices WHERE id=%s',(b.invoice_id,))
        assert ops.latest_source_evidence(c.fetchone()[0])['source_customer_id']=='97052'


@pytest.mark.parametrize('change',['tenant','customer','public_id','uuid','deleted','manifest','capture_source','envelope_hash','fact_hash','prior_customer_drift','missing_order','wrong_order_source','cancelled_order','deleted_invoice','deleted_customer'])
def test_real_bootstrap_identity_and_drift_holds(pg,change):
    conn,_=pg;b,_p,doc,old,order=bootstrap_fixture(conn)
    if change=='tenant':b.tenant_id=uuid4()
    elif change=='customer':b.source_customer_id=uuid4()
    elif change=='public_id':doc['sourceEvidence']['source_customer_id']='97053'
    elif change=='uuid':doc['sourceEvidence']['source_customer_uuid']=str(uuid4())
    elif change=='deleted':doc['sourceEvidence']['source_customer_deleted']=True
    elif change=='manifest':doc['sourceEvidence']['invoice_manifest']['invoice_ids'].append('other')
    elif change=='capture_source':doc['sourceEvidence']['invoice_id']='wrong'
    elif change=='envelope_hash':b.expected_envelope_sha256='wrong'
    elif change=='fact_hash':b.expected_evidence_sha256='wrong'
    else:
        with conn.cursor() as c:
            if change=='prior_customer_drift':
                facts=old['observations'][0]['evidence'];facts.update(source_customer_id='97051',source_customer_uuid=b.expected_source_customer_uuid,source_customer_deleted=False,source_customer_binding_kind='embedded_service_customer')
                old['observations'][0]['sha256']=ops._digest(facts)
                b.expected_envelope_sha256=ops.digest(old);b.expected_evidence_sha256=old['observations'][0]['sha256']
                c.execute('UPDATE invoices SET ets_source_evidence=%s',(psycopg2.extras.Json(old),))
            elif change=='missing_order':c.execute('DELETE FROM repair_orders')
            elif change=='wrong_order_source':c.execute("UPDATE repair_orders SET source='native'")
            elif change=='cancelled_order':c.execute("UPDATE repair_orders SET status='cancelled'")
            elif change=='deleted_invoice':c.execute('UPDATE invoices SET deleted_at=now()')
            elif change=='deleted_customer':c.execute('UPDATE customers SET deleted_at=now()')
        conn.commit()
    with pytest.raises(ValueError):ops.bootstrap(conn,b,doc)
    conn.rollback()
    with conn.cursor() as c:
        c.execute('SELECT ets_source_evidence FROM invoices');assert c.fetchone()[0]==old


def test_real_bootstrap_financial_lock_and_related_row_rollback(pg):
    conn,connect=pg;b,_p,doc,old,order=bootstrap_fixture(conn);other=connect()
    with other.cursor() as c:importer._lock_source_money(c,b.tenant_id)
    with pytest.raises(ValueError,match='busy'):ops.bootstrap(conn,b,doc)
    conn.rollback();other.rollback()
    with conn.cursor() as c:
        c.execute("CREATE FUNCTION bad_customer() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN UPDATE customers SET ets_external_id='WRONG'; RETURN NEW; END $$")
        c.execute('CREATE TRIGGER simulate_customer_write AFTER UPDATE ON invoices FOR EACH ROW EXECUTE FUNCTION bad_customer()')
    conn.commit()
    with pytest.raises(ValueError,match='Financial state changed'):ops.bootstrap(conn,b,doc)
    conn.rollback()
    with conn.cursor() as c:
        c.execute('SELECT ets_external_id FROM customers');assert c.fetchone()[0]=='97052'
        c.execute('SELECT ets_source_evidence FROM invoices');assert c.fetchone()[0]==old


@pytest.mark.parametrize('state',['prepared','active','source_conflict','closed'])
@pytest.mark.parametrize('deleted',[False,True])
def test_real_bootstrap_never_bypasses_permanent_handoff(pg,state,deleted):
    conn,_=pg;b,prepared,doc,old,order=bootstrap_fixture(conn)
    with conn.cursor() as c:
        # Different local invoice UUID still fences the same remote debt.
        c.execute('INSERT INTO source_debt_handoffs VALUES(%s,%s,%s,%s,NULL,%s,%s,%s,%s,%s,now(),1,%s,%s)',(prepared.handoff_id,b.tenant_id,uuid4(),order,'shop','506423','468019','1821','1687',state,datetime.now(timezone.utc) if deleted else None))
    conn.commit()
    with pytest.raises(ValueError,match='Canonical handoff exists'):ops.bootstrap(conn,b,doc)
    conn.rollback()


def test_real_bootstrap_accepts_proven_archived_source_without_restoring_order(pg):
    conn,_=pg;b,_p,doc,_old,order=bootstrap_fixture(conn)
    with conn.cursor() as c:
        c.execute('UPDATE repair_orders SET deleted_at=now() WHERE id=%s',(order,))
    conn.commit()
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as c:
        before=ops.fingerprint(c,b.tenant_id,[b.invoice_id],[order],[b.source_customer_id])
    conn.rollback();b.commit=False;conn.set_session(readonly=True)
    assert ops.bootstrap(conn,b,doc)['mode']=='bootstrap-dry-run'
    conn.rollback();conn.set_session(readonly=False);b.commit=True
    assert ops.bootstrap(conn,b,doc)['financial_state_unchanged'];conn.commit()
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as c:
        assert ops.fingerprint(c,b.tenant_id,[b.invoice_id],[order],[b.source_customer_id])==before
        c.execute('SELECT deleted_at FROM repair_orders WHERE id=%s',(order,))
        assert c.fetchone()['deleted_at'] is not None
