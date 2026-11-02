from copy import deepcopy
from datetime import datetime, timezone, timedelta
from types import SimpleNamespace
from uuid import uuid4
import sqlite3
import pytest
from scripts.easytruck_sync import import_to_truckpitstop as importer
from scripts.easytruck_sync.source_evidence import normalize_source_evidence
from app.services.ets_source_evidence import normalize_source_evidence as app_normalize
from scripts.easytruck_sync.persist_invoice_evidence import validate_capture


def evidence():
    return {'schema_version':1,'source':'easy_truck_shop','ets_shop_id':'shop',
            'service_id':'1821','service_internal_id':'506423','invoice_service_id':'506423',
            'invoice_id':'468019','invoice_number':'1687','payment_lines':[],
            'invoice_manifest':{'complete':True,'evidence_kind':'verified_source_service_invoice_manifest','service_internal_id':'506423','invoice_ids':['468019']}}


@pytest.mark.parametrize('normalizer',[normalize_source_evidence,app_normalize])
def test_marker_is_whitelisted_and_dates_are_not_guessed(normalizer):
    source=evidence()
    source['payment_lines']=[{'id':'allocation','amount':{'amount':'10','currency':'USD'},'payment':{
        'id':'payment','date_source':'2026-11-01T12:00:00Z','date_semantics':'source_datetime_utc',
        'dbn_receipt_reference':'DBN-RECEIPT:ABCDEF01-2345-6789-ABCD-EF0123456789','notes':'PRIVATE'}}]
    out=normalizer(source)['payment_lines'][0]['payment']
    assert out['dbn_receipt_reference']=='DBN-RECEIPT:abcdef01-2345-6789-abcd-ef0123456789'
    assert out['date_semantics']=='source_datetime_utc'
    assert 'PRIVATE' not in str(out)
    for date in ['2026-02-30T12:00:00Z','2026-11-01','2026-11-01T12:00:00','2026-11-01T12:00:00-04:00']:
        source['payment_lines'][0]['payment']['date_source']=date
        assert normalizer(source)['payment_lines'][0]['payment']['date_semantics']=='source_datetime_unverified'
    source['payment_lines'][0]['payment']['dbn_receipt_reference']='PRIVATE DBN-RECEIPT:abcdef01-2345-6789-abcd-ef0123456789'
    assert 'dbn_receipt_reference' not in normalizer(source)['payment_lines'][0]['payment']


class Cursor:
    def __init__(self,db,lock=True):self.db=db;self.lock=lock;self.special=None;self.last=None;self.writes=[]
    def execute(self,sql,params=()):
        if 'pg_try_advisory_xact_lock' in sql:self.special=(self.lock,);return
        if 'to_regclass' in sql:
            self.special=('source_debt_handoffs' if self.db.execute("select 1 from sqlite_master where name='source_debt_handoffs'").fetchone() else None,);return
        self.special=None
        if sql.lstrip().split()[0] in ('INSERT','UPDATE','DELETE'):self.writes.append(sql)
        self.last=self.db.execute(sql.replace('%s','?'),tuple(str(v) if hasattr(v,'hex') and not isinstance(v,str) else v for v in params))
    def fetchone(self):return self.special if self.special is not None else self.last.fetchone()


@pytest.fixture
def guarded():
    db=sqlite3.connect(':memory:')
    db.execute('create table source_debt_handoffs(tenant_id text, source_dbn_invoice_id text, ets_shop_id text, ets_invoice_internal_id text,source_service_number text,source_invoice_number text,state text,deleted_at text)')
    return db,uuid4(),uuid4()


@pytest.mark.parametrize('state',['prepared','active','source_conflict','closed'])
@pytest.mark.parametrize('deleted',[None,'2026-11-01'])
def test_imported_creation_and_backfill_cannot_recreate_handed_off_debt(guarded,state,deleted):
    db,tenant,invoice=guarded
    db.execute('insert into source_debt_handoffs values(?,?,?,?,?,?,?,?)',(str(tenant),str(invoice),'shop','468019','1821','1687',state,deleted))
    cur=Cursor(db);stats={}
    importer._create_invoice_and_payments(cur,tenant,uuid4(),'ETS-1821-x','1821',{'1821':{'invoiceNumber':'1687','total':'268.44','sourceEvidence':evidence()}},set(),stats,datetime.now())
    assert stats=={'source_debt_handoff_skipped':1}
    assert cur.writes==[]
    assert importer._source_debt_owned(cur,tenant,'1821',None) # missing capture never unlocks the same known service
    assert not importer._source_debt_owned(cur,uuid4(),'1821',{'invoiceNumber':'1687','sourceEvidence':evidence()})


def test_legacy_payment_sync_is_fenced_before_amount_matching(guarded):
    db,tenant,invoice=guarded
    db.execute('insert into source_debt_handoffs values(?,?,?,?,?,?,?,?)',(str(tenant),str(invoice),'shop','468019','1821','1687','active',None))
    class Reader:
        def execute(self,*args):pass
        def fetchall(self):return [{'id':invoice,'invoice_number':'ETSINV-1687','total_amount':'268.44','status':'sent','paid_at':None}]
    cur=Cursor(db);stats={}
    importer._sync_payments_for_existing_invoices(None,cur,Reader(),tenant,{'1821':{'invoiceNumber':'1687','payments':[{'amount':'268.44'}],'sourceEvidence':evidence()}},stats,datetime.now())
    assert cur.writes==[] and stats=={'source_debt_handoff_skipped':1}


def test_busy_financial_lock_aborts_before_any_source_write(guarded):
    db,tenant,_=guarded;cur=Cursor(db,False)
    with pytest.raises(RuntimeError,match='busy'):
        importer._create_invoice_and_payments(cur,tenant,uuid4(),'order','1821',{},set(),{},datetime.now())
    assert cur.writes==[]


def test_evidence_commit_requires_exact_post_ack_identity_and_manifest():
    tenant=uuid4();now=datetime.now(timezone.utc)
    handoff={'ets_shop_id':'shop','source_service_number':'1821','ets_service_internal_id':'506423','ets_invoice_internal_id':'468019','source_invoice_number':'1687','owner_acknowledged_at':now-timedelta(minutes=2)}
    facts=evidence();facts['observed_at_source']=(now-timedelta(minutes=1)).isoformat()
    doc={'schema_version':1,'capture_kind':'ets_target_invoice_evidence','tenant_id':str(tenant),'sourceEvidence':facts}
    assert validate_capture(doc,tenant,handoff,now)['invoice_id']=='468019'
    for key,val in [('invoice_id','other'),('observed_at_source',(now-timedelta(minutes=3)).isoformat()),('observed_at_source',(now+timedelta(minutes=1)).isoformat()),('invoice_manifest',None)]:
        bad=deepcopy(doc);bad['sourceEvidence'][key]=val
        with pytest.raises(ValueError):validate_capture(bad,tenant,handoff,now)
    with pytest.raises(ValueError):validate_capture(doc,uuid4(),handoff,now)

@pytest.mark.parametrize('normalizer',[normalize_source_evidence,app_normalize])
def test_customer_proof_is_optional_complete_and_digest_bound(normalizer):
    from scripts.easytruck_sync.source_evidence import _digest
    source=evidence();old=normalizer(source)
    assert 'source_customer_id' not in old
    proof=dict(source_customer_id='97052',source_customer_uuid='02104722-a300-48a5-ba98-0eab3b2fb32e',source_customer_deleted=False,source_customer_binding_kind='embedded_service_customer')
    source.update(proof);source['customer_name']='PRIVATE';source['source_customer_internal_id']='GUESS'
    out=normalizer(source)
    assert all(out[k]==v for k,v in proof.items())
    assert 'PRIVATE' not in str(out) and 'source_customer_internal_id' not in out
    assert _digest(out)!=_digest(old)
    source['source_customer_id']='97053';assert _digest(normalizer(source))!=_digest(out)
    del source['source_customer_uuid'];assert 'source_customer_id' not in normalizer(source)
