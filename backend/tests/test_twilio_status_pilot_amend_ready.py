"""One-time unused-slot correction; private temp state and fake isolated rows only."""
import asyncio
import copy
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import sys
from uuid import UUID,uuid4
import pytest
import pytest_asyncio
from sqlalchemy import select,update

SCRIPTS=Path(__file__).resolve().parents[2]/'scripts'
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0,str(SCRIPTS))
import twilio_status_pilot_amend_ready as amendment
pilot=amendment.pilot
FAKE_RECIPIENT='+15005550101'
ACCOUNT='AC'+'a'*32
TEST_DATABASE='twilio_status_pilot_amend_test_20261020'
pytestmark=pytest.mark.skipif(not os.getenv('DATABASE_URL','').endswith('/'+TEST_DATABASE),reason='fresh dedicated amendment test DB only')


@pytest_asyncio.fixture
async def prepared(monkeypatch,tmp_path):
    import dotenv,twilio.rest,requests.sessions
    def forbidden(*args,**kwargs):
        raise AssertionError('No provider or credential access in amendment tests')
    monkeypatch.setattr(dotenv,'dotenv_values',forbidden)
    monkeypatch.setattr(twilio.rest,'Client',forbidden)
    monkeypatch.setattr(requests.sessions.Session,'request',forbidden)
    monkeypatch.setattr(requests.sessions.Session,'send',forbidden)
    monkeypatch.setattr(pilot,'provider',forbidden)
    monkeypatch.setattr(pilot,'DATABASE',TEST_DATABASE)
    monkeypatch.setattr(pilot,'STATE_DIR',tmp_path)
    monkeypatch.setattr(pilot,'AUTHORIZATION',tmp_path/'authorization.json')
    monkeypatch.setattr(pilot,'PLAN',tmp_path/'plan.json')
    monkeypatch.setattr(pilot,'LEDGER',tmp_path/'ledger.sqlite3')
    pilot.AUTHORIZATION.write_text(json.dumps({'schema':1,'recipient':FAKE_RECIPIENT,'recipient_sha256':pilot.fingerprint(FAKE_RECIPIENT)}))
    pilot.AUTHORIZATION.chmod(0o600)
    new=pilot.make_plan(pilot.fingerprint(ACCOUNT))
    old=copy.deepcopy(new)
    old['events']['ready_pickup_sms']['body']=f"TEST DieselBridge: simulated ready for pickup. No real repair changed. Please reply {old['reply_token']}."
    pilot.initialize_guard(new)
    sid='SM'+uuid4().hex
    with sqlite3.connect(pilot.LEDGER) as connection:
        connection.execute('UPDATE approved SET binding=? WHERE slot=1',(pilot.plan_hash(old),))
        connection.execute('INSERT INTO attempts VALUES(?,?)',('work_started_sms',pilot.plan_hash(old)))
        connection.execute('INSERT INTO receipts VALUES(?,?)',('work_started_sms',sid))
    pilot.PLAN.write_text(json.dumps(old));pilot.PLAN.chmod(0o600)
    from app.db.session import AsyncSessionLocal,engine
    from app.db.models.tenant import Tenant
    from app.db.models.customer import Customer
    from app.db.models.sms_message import SMSMessage,SMSDeliveryStatus
    from app.db.models.notification import Notification,NotificationStatus
    from app.services.automated_sms_service import enqueue_automated_sms
    async with AsyncSessionLocal() as db:
        db.add(Tenant(id=UUID(old['tenant_id']),name='Amend synthetic',slug='amend-test-'+old['run_id'],sms_phone_number=pilot.SENDER,sms_enabled=True,messaging_enabled=True))
        await db.flush()
        db.add(Customer(id=UUID(old['customer_id']),tenant_id=UUID(old['tenant_id']),first_name='Synthetic',last_name='Owner',phone=FAKE_RECIPIENT,email=old['run_id']+'@example.test'))
        await db.flush()
        operation=await enqueue_automated_sms(db,tenant_id=UUID(old['tenant_id']),domain_event_id=old['events']['work_started_sms']['domain_event_id'],template_name='work_started_sms',to=FAKE_RECIPIENT,body=old['events']['work_started_sms']['body'],customer_id=UUID(old['customer_id']))
        operation.state='accepted';operation.attempt_count=1;operation.delivery_status='delivered';operation.provider_message_sid=sid
        message=await db.get(SMSMessage,operation.message_id)
        message.twilio_message_sid=sid;message.delivery_status=SMSDeliveryStatus.DELIVERED
        notification=await db.get(Notification,operation.notification_id);notification.status=NotificationStatus.DELIVERED
        await db.commit()
        operation_id=operation.id
    try:
        yield old,new,sid,operation_id
    finally:
        async with AsyncSessionLocal() as db:
            await db.execute(update(Tenant).where(Tenant.id==UUID(old['tenant_id'])).values(sms_phone_number=None));await db.commit()
        await engine.dispose()


@pytest.mark.asyncio
async def test_one_time_amendment_changes_only_unused_body_and_global_hash(prepared):
    old,new,sid,first_id=prepared
    original_bytes=pilot.PLAN.read_bytes()
    with sqlite3.connect(pilot.LEDGER) as connection:
        claims=connection.execute('SELECT * FROM attempts').fetchall()
        receipts=connection.execute('SELECT * FROM receipts').fetchall()
    await amendment.amend_ready_copy()
    actual=json.loads(pilot.PLAN.read_text())
    assert actual==new
    assert actual['events']['work_started_sms']==old['events']['work_started_sms']
    assert 'Ref '+old['reply_token'] in actual['events']['ready_pickup_sms']['body']
    assert 'Please reply' not in actual['events']['ready_pickup_sms']['body']
    with sqlite3.connect(pilot.LEDGER) as connection:
        assert connection.execute('SELECT * FROM attempts').fetchall()==claims
        assert connection.execute('SELECT * FROM receipts').fetchall()==receipts
        audit=connection.execute('SELECT old_hash,new_hash,first_operation_id,state FROM ready_copy_amendments').fetchone()
        assert audit==(pilot.plan_hash(old),pilot.plan_hash(new),str(first_id),'complete')
    pilot.validate_plan(actual)
    with pytest.raises(RuntimeError):
        await amendment.amend_ready_copy()


@pytest.mark.asyncio
@pytest.mark.parametrize('fault',['first_pending','first_undelivered','first_attempt_zero','first_sid','second_op','second_claim','second_receipt','wrong_hash','changed_plan'])
async def test_amendment_refuses_any_nonexact_state(prepared,fault):
    old,new,sid,first_id=prepared
    from app.db.session import AsyncSessionLocal
    from app.db.models.automated_sms import AutomatedSMSOperation
    from app.services.automated_sms_service import enqueue_automated_sms
    if fault.startswith('first_') or fault=='second_op':
        async with AsyncSessionLocal() as db:
            first=await db.get(AutomatedSMSOperation,first_id)
            if fault=='first_pending': first.state='pending'
            elif fault=='first_undelivered': first.delivery_status='undelivered'
            elif fault=='first_attempt_zero': first.attempt_count=0
            elif fault=='first_sid': first.provider_message_sid='SM'+uuid4().hex
            else:
                await enqueue_automated_sms(db,tenant_id=UUID(old['tenant_id']),domain_event_id=old['events']['ready_pickup_sms']['domain_event_id'],template_name='ready_pickup_sms',to=FAKE_RECIPIENT,body=old['events']['ready_pickup_sms']['body'],customer_id=UUID(old['customer_id']))
            await db.commit()
    elif fault=='changed_plan':
        changed=copy.deepcopy(old);changed['events']['work_started_sms']['body']='Changed first copy'
        pilot.PLAN.write_text(json.dumps(changed))
    else:
        with sqlite3.connect(pilot.LEDGER) as connection:
            if fault=='second_claim': connection.execute('INSERT INTO attempts VALUES(?,?)',('ready_pickup_sms',pilot.plan_hash(old)))
            elif fault=='second_receipt': connection.execute('INSERT INTO receipts VALUES(?,?)',('ready_pickup_sms','SM'+uuid4().hex))
            else: connection.execute('UPDATE approved SET binding=? WHERE slot=1',('a'*64,))
    before=pilot.PLAN.read_bytes()
    with pytest.raises(RuntimeError):
        await amendment.amend_ready_copy()
    assert pilot.PLAN.read_bytes()==before
    assert not pilot.PLAN.with_name('plan.ready-amendment.tmp').exists()


@pytest.mark.asyncio
async def test_crash_after_ledger_commit_blocks_all_new_claims(prepared,monkeypatch):
    old,new,sid,first_id=prepared
    def fail(*args):
        raise OSError('simulated file replacement failure')
    monkeypatch.setattr(amendment.os,'replace',fail)
    with pytest.raises(OSError):
        await amendment.amend_ready_copy()
    assert json.loads(pilot.PLAN.read_text())==old
    with sqlite3.connect(pilot.LEDGER) as connection:
        assert connection.execute('SELECT state FROM ready_copy_amendments').fetchone()[0]=='committing'
        assert connection.execute('SELECT count(*) FROM attempts').fetchone()[0]==1
    with pytest.raises(RuntimeError,match='Partial'):
        pilot.validate_plan(new)
    with pytest.raises(RuntimeError):
        await amendment.amend_ready_copy()


@pytest.mark.asyncio
async def test_concurrent_amendments_have_one_marker_and_no_budget_changes(prepared):
    async def run():
        try:
            await amendment.amend_ready_copy();return True
        except (RuntimeError,sqlite3.OperationalError):
            return False
    results=await asyncio.gather(run(),run())
    assert sum(results)==1
    with sqlite3.connect(pilot.LEDGER) as connection:
        assert connection.execute('SELECT count(*) FROM ready_copy_amendments').fetchone()[0]==1
        assert connection.execute('SELECT count(*) FROM attempts').fetchone()[0]==1
