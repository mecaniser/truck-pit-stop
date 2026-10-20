"""Closed pilot tests: never read real credentials, state or provider endpoints."""
import copy
import importlib.util
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4
import os
import json
import sqlite3
import pytest
import pytest_asyncio

SPEC = importlib.util.spec_from_file_location('twilio_status_pilot_tests', Path(__file__).resolve().parents[2]/'scripts/twilio_status_pilot.py')
pilot = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(pilot)
ACCOUNT = 'AC'+'1'*32
TEST_RECIPIENT = '+15005550101'


@pytest.fixture(autouse=True)
def fictional_recipient_runtime(monkeypatch, tmp_path):
    if os.getenv('DATABASE_URL','').endswith('/twilio_status_pilot_amend_test_20261020'):
        monkeypatch.setattr(pilot,'DATABASE','twilio_status_pilot_amend_test_20261020')
    state = tmp_path/'private-state'
    state.mkdir(mode=0o700)
    authorization = state/'authorization.json'
    authorization.write_text(json.dumps({'schema':1,'recipient':TEST_RECIPIENT,'recipient_sha256':pilot.fingerprint(TEST_RECIPIENT)}))
    authorization.chmod(0o600)
    monkeypatch.setattr(pilot, 'STATE_DIR', state)
    monkeypatch.setattr(pilot, 'AUTHORIZATION', authorization)
    monkeypatch.setattr(pilot, 'PLAN', state/'plan.json')
    monkeypatch.setattr(pilot, 'LEDGER', state/'ledger.sqlite3')
    def forbidden(*args, **kwargs):
        raise AssertionError('Real credential reads and provider HTTP are forbidden in tests')
    import dotenv
    import twilio.rest
    import requests.sessions
    monkeypatch.setattr(dotenv, 'dotenv_values', forbidden)
    monkeypatch.setattr(twilio.rest, 'Client', forbidden)
    monkeypatch.setattr(requests.sessions.Session, 'request', forbidden)
    monkeypatch.setattr(requests.sessions.Session, 'send', forbidden)
    return authorization


@pytest.fixture
def approved(tmp_path):
    plan = pilot.make_plan(pilot.fingerprint(ACCOUNT))
    ledger = tmp_path/'ledger.sqlite3'
    pilot.initialize_guard(plan, ledger)
    return plan, ledger


def claim(plan, ledger, event='work_started_sms', **overrides):
    args = dict(body=plan['events'][event]['body'], from_number=pilot.SENDER, to_number=TEST_RECIPIENT, account_hash=plan['account_hash'])
    args.update(overrides)
    pilot.claim_provider_call(plan, event, **args, ledger=ledger)


@pytest.mark.parametrize('field,value', [('to_number','+15005550001'),('from_number','+15005550002'),('body','Unapproved text'),('account_hash','a'*64)])
def test_payload_changes_never_claim(approved, field, value):
    plan, ledger = approved
    with pytest.raises(RuntimeError):
        claim(plan, ledger, **{field:value})
    with sqlite3.connect(ledger) as db:
        assert db.execute('SELECT count(*) FROM attempts').fetchone()[0] == 0


def test_two_event_permanent_budget_concurrent_and_restart(approved):
    plan, ledger = approved
    def attempt(event):
        try:
            claim(plan, ledger, event)
            return True
        except sqlite3.IntegrityError:
            return False
    for event in pilot.EVENTS:
        with ThreadPoolExecutor(max_workers=8) as pool:
            assert sum(pool.map(attempt,[event]*8)) == 1
        assert attempt(event) is False
    with sqlite3.connect(ledger) as db:
        assert db.execute('SELECT count(*) FROM attempts').fetchone()[0] == 2
    with pytest.raises(FileExistsError):
        pilot.initialize_guard(pilot.make_plan(plan['account_hash']), ledger)


@pytest.mark.parametrize('mutation', ['recipient','sender','account_hash','created_at','expires_at','reply_token','event','body','run_id','purpose'])
def test_changed_plan_cannot_expand_or_reset_budget(approved, mutation):
    plan, ledger = approved
    changed = copy.deepcopy(plan)
    if mutation == 'event':
        changed['events']['invoice_reminder_sms'] = changed['events'].pop('ready_pickup_sms')
    elif mutation == 'body':
        changed['events']['work_started_sms']['body'] = 'Real repair completed'
    elif mutation == 'expires_at':
        changed[mutation] = (datetime.fromisoformat(changed[mutation])+timedelta(days=1)).isoformat()
    elif mutation == 'created_at':
        changed[mutation] = (datetime.fromisoformat(changed[mutation])-timedelta(seconds=1)).isoformat()
    elif mutation == 'run_id':
        changed[mutation] = str(uuid4())
    elif mutation == 'purpose':
        changed[mutation] = 'customer_automation'
    elif mutation == 'reply_token':
        changed[mutation] = 'TPS-PILOT-ABCDEF00'
    elif mutation == 'account_hash':
        changed[mutation] = 'b'*64
    else:
        changed[mutation] = '+15005550001'
    with pytest.raises((RuntimeError, ValueError)):
        pilot.validate_plan(changed, ledger)
    with pytest.raises(RuntimeError):
        pilot.claim_provider_call(changed, 'work_started_sms', body='Other',from_number=pilot.SENDER,to_number=TEST_RECIPIENT,account_hash=plan['account_hash'],ledger=ledger)


def test_expiry_blocks_send_but_status_can_validate_immutable_old_plan(approved):
    plan, ledger = approved
    after = datetime.fromisoformat(plan['expires_at'])+timedelta(seconds=1)
    with pytest.raises(RuntimeError):
        pilot.validate_shape(plan, now=after)
    pilot.validate_shape(plan, now=after, require_unexpired=False)
    assert all(item['body'].isascii() and item['body'].startswith('TEST DieselBridge:') and 'No real repair changed' in item['body'] for item in plan['events'].values())
    assert 'Reply STOP to opt out.' in plan['events']['work_started_sms']['body']
    assert plan['purpose'] == 'owner_only_technical_test'


def test_missing_ledger_and_symlink_state_fail_closed(approved, tmp_path):
    plan, ledger = approved
    with pytest.raises(FileNotFoundError):
        pilot.validate_plan(plan, tmp_path/'missing.sqlite3')
    link = tmp_path/'link'; link.symlink_to(ledger)
    with pytest.raises(RuntimeError):
        pilot.validate_plan(plan, link)
    ledger.chmod(0o644)
    with pytest.raises(RuntimeError):
        pilot.validate_plan(plan, ledger)


def test_provider_receipt_scope_and_expected_sid(approved):
    plan, _ = approved
    data = dict(sid='SM'+'2'*32,account_sid=ACCOUNT,from_=pilot.SENDER,to=TEST_RECIPIENT,body=plan['events']['work_started_sms']['body'])
    pilot.validate_receipt(plan,'work_started_sms',SimpleNamespace(**data),expected_sid=data['sid'])
    for key,value in [('sid','SM'+'3'*32),('account_sid','AC'+'4'*32),('to','+15005550001'),('from_','+15005550002'),('body','Other')]:
        with pytest.raises(RuntimeError):
            pilot.validate_receipt(plan,'work_started_sms',SimpleNamespace(**{**data,key:value}),expected_sid=data['sid'])


def test_exact_reply_scope_session_and_time(approved):
    plan, _ = approved
    values = dict(sid='SM'+'5'*32,account_sid=ACCOUNT,direction='inbound',from_=TEST_RECIPIENT,to=pilot.SENDER,
        body=plan['reply_token'],date_sent=datetime.fromisoformat(plan['created_at'])+timedelta(seconds=1))
    assert pilot.valid_reply(plan,SimpleNamespace(**values))
    changes = [('sid','bad'),('account_sid','AC'+'6'*32),('direction','outbound-api'),('from_','+15005550001'),
        ('to','+15005550002'),('body',plan['reply_token']+' unrelated'),('date_sent',datetime.fromisoformat(plan['created_at'])-timedelta(seconds=1)),
        ('date_sent',datetime.fromisoformat(plan['expires_at'])+timedelta(seconds=1)),('date_sent',datetime.now())]
    for key,value in changes:
        assert not pilot.valid_reply(plan,SimpleNamespace(**{**values,key:value}))


@pytest.mark.parametrize('setting', ['SMS_TENANT_ROUTING_ENABLED','SMS_AUTOMATION_OUTBOX_ENABLED','SMS_RECOVERY_ENABLED','TWILIO_ACCOUNT_SID'])
def test_live_environment_rejects_enabled_flags_or_server_credentials(monkeypatch, setting):
    from app.core.config import settings
    monkeypatch.setenv('TWILIO_STATUS_PILOT_LOCAL','1')
    monkeypatch.setenv('COMMUNICATIONS_ISOLATED_LOCAL','1')
    monkeypatch.setattr(settings,'DATABASE_URL','postgresql+asyncpg://comms_local:synthetic@127.0.0.1:55460/'+pilot.DATABASE)
    monkeypatch.setattr(settings,'ENVIRONMENT','development')
    for name in ('SMS_TENANT_ROUTING_ENABLED','SMS_AUTOMATION_OUTBOX_ENABLED','SMS_RECOVERY_ENABLED'):
        monkeypatch.setattr(settings,name,False)
    monkeypatch.setattr(settings,'TWILIO_ACCOUNT_SID','')
    monkeypatch.setattr(settings,'TWILIO_AUTH_TOKEN','')
    pilot.assert_isolated()
    monkeypatch.setattr(settings,setting,'ACsynthetic' if setting=='TWILIO_ACCOUNT_SID' else True)
    with pytest.raises(RuntimeError):
        pilot.assert_isolated()


def test_other_database_rejected(monkeypatch):
    from app.core.config import settings
    monkeypatch.setenv('TWILIO_STATUS_PILOT_LOCAL','1')
    monkeypatch.setenv('COMMUNICATIONS_ISOLATED_LOCAL','1')
    monkeypatch.setattr(settings,'DATABASE_URL','postgresql+asyncpg://comms_local:synthetic@127.0.0.1:55460/communications_local')
    with pytest.raises(RuntimeError):
        pilot.assert_isolated()


isolated = pytest.mark.skipif(os.getenv('TWILIO_STATUS_PILOT_LOCAL') != '1',reason='dedicated isolated pilot PostgreSQL required')


@pytest_asyncio.fixture
async def isolated_fixture(monkeypatch, approved, tmp_path):
    from app.db.session import AsyncSessionLocal, engine
    from app.db.models.tenant import Tenant
    from app.db.models.customer import Customer
    from uuid import UUID
    plan, ledger = approved
    monkeypatch.setattr(pilot,'LEDGER',ledger)
    pilot.assert_isolated()
    from sqlalchemy import update
    async with AsyncSessionLocal() as db:
        db.add(Tenant(id=UUID(plan['tenant_id']), name='Test sealed pilot',slug='test-pilot-'+plan['run_id'],
            sms_phone_number=pilot.SENDER,sms_enabled=True,messaging_enabled=True))
        await db.flush()
        db.add(Customer(id=UUID(plan['customer_id']),tenant_id=UUID(plan['tenant_id']),first_name='Test',last_name='Recipient',
            phone=TEST_RECIPIENT,email=plan['run_id']+'@example.test'))
        await db.commit()
    try:
        yield plan, ledger
    finally:
        async with AsyncSessionLocal() as db:
            await db.execute(update(Tenant).where(Tenant.id==UUID(plan['tenant_id'])).values(sms_phone_number=None))
            await db.commit()
        await engine.dispose()


@isolated
@pytest.mark.asyncio
async def test_real_outbox_two_events_and_replay_cross_provider_once_each(isolated_fixture,monkeypatch):
    from app.db.session import AsyncSessionLocal
    from app.db.models.automated_sms import AutomatedSMSOperation
    from app.db.models.repair_order import RepairOrder
    from sqlalchemy import select, func
    from uuid import UUID
    plan, ledger = isolated_fixture
    calls=[]
    class Messages:
        def create(self,**kwargs):
            event = next(event for event in pilot.EVENTS if plan['events'][event]['body']==kwargs['body'])
            calls.append(event)
            return SimpleNamespace(sid='SM'+uuid4().hex,account_sid=ACCOUNT,
                from_=kwargs['from_'],to=kwargs['to'],body=kwargs['body'],status='queued')
    monkeypatch.setattr(pilot,'provider',lambda:(SimpleNamespace(messages=Messages()),plan['account_hash']))
    for event in pilot.EVENTS:
        await pilot.send(plan,event)
        await pilot.send(plan,event)
    assert calls == list(pilot.EVENTS)
    with sqlite3.connect(ledger) as db:
        assert db.execute('SELECT count(*) FROM attempts').fetchone()[0]==2
    async with AsyncSessionLocal() as db:
        operations=(await db.scalars(select(AutomatedSMSOperation).where(AutomatedSMSOperation.tenant_id==UUID(plan['tenant_id'])))).all()
        assert len(operations)==2 and all(op.state=='accepted' and op.attempt_count==1 for op in operations)
        assert await db.scalar(select(func.count()).select_from(RepairOrder).where(RepairOrder.tenant_id==UUID(plan['tenant_id'])))==0


@isolated
@pytest.mark.asyncio
async def test_timeout_consumes_claim_and_never_retries(isolated_fixture,monkeypatch):
    plan, ledger = isolated_fixture
    calls=[]
    class Messages:
        def create(self,**kwargs):
            calls.append(kwargs)
            raise TimeoutError('simulated uncertain transport')
    monkeypatch.setattr(pilot,'provider',lambda:(SimpleNamespace(messages=Messages()),plan['account_hash']))
    await pilot.send(plan,'work_started_sms')
    await pilot.send(plan,'work_started_sms')
    assert len(calls)==1
    with sqlite3.connect(ledger) as db:
        assert db.execute('SELECT count(*) FROM attempts').fetchone()[0]==1


def test_live_token_without_account_is_rejected_before_provider_access(monkeypatch):
    from app.core.config import settings
    monkeypatch.setenv('TWILIO_STATUS_PILOT_LOCAL','1')
    monkeypatch.setenv('COMMUNICATIONS_ISOLATED_LOCAL','1')
    monkeypatch.setenv('LOCAL_WEBHOOK_SECRET','synthetic-webhook-only')
    monkeypatch.setattr(settings,'DATABASE_URL','postgresql+asyncpg://comms_local:synthetic@127.0.0.1:55460/'+pilot.DATABASE)
    monkeypatch.setattr(settings,'ENVIRONMENT','development')
    monkeypatch.setattr(settings,'TWILIO_ACCOUNT_SID','')
    for name in ('SMS_TENANT_ROUTING_ENABLED','SMS_AUTOMATION_OUTBOX_ENABLED','SMS_RECOVERY_ENABLED'):
        monkeypatch.setattr(settings,name,False)
    monkeypatch.setattr(settings,'TWILIO_AUTH_TOKEN','synthetic-webhook-only')
    pilot.assert_isolated()
    monkeypatch.setattr(settings,'TWILIO_AUTH_TOKEN','unapproved-provider-token')
    with pytest.raises(RuntimeError):
        pilot.assert_isolated()
    with pytest.raises(RuntimeError):
        pilot.provider()


@isolated
@pytest.mark.asyncio
async def test_reply_import_is_pinned_and_replayed_without_global_lookup(isolated_fixture):
    from app.db.session import AsyncSessionLocal
    from app.db.models.message_thread import MessageThread
    from app.db.models.sms_message import SMSMessage
    from sqlalchemy import select, func
    from uuid import UUID
    plan, ledger=isolated_fixture
    async with AsyncSessionLocal() as db:
        thread=MessageThread(tenant_id=UUID(plan['tenant_id']),customer_id=UUID(plan['customer_id']),customer_phone=TEST_RECIPIENT)
        db.add(thread);await db.commit()
        reply=SimpleNamespace(sid='SM'+uuid4().hex,account_sid=ACCOUNT,direction='inbound',from_=TEST_RECIPIENT,to=pilot.SENDER,
            body=plan['reply_token'],date_sent=datetime.now(timezone.utc))
        first=await pilot.import_reply(db,plan,reply);await db.commit()
        second=await pilot.import_reply(db,plan,reply);await db.commit()
        assert first[0]==second[0] and first[1] is False and second[1] is True
        assert await db.scalar(select(func.count()).select_from(SMSMessage).where(SMSMessage.thread_id==thread.id))==1
        assert thread.unread_count_staff==1


@isolated
@pytest.mark.asyncio
@pytest.mark.parametrize('change',['foreign_sender','changed_customer','opt_out','missing_thread'])
async def test_reply_import_identity_changes_fail_without_writes(isolated_fixture,change):
    from app.db.session import AsyncSessionLocal
    from app.db.models.tenant import Tenant
    from app.db.models.customer import Customer
    from app.db.models.message_thread import MessageThread
    from app.db.models.sms_message import SMSMessage
    from sqlalchemy import select,func
    from uuid import UUID
    plan,ledger=isolated_fixture
    async with AsyncSessionLocal() as db:
        if change!='missing_thread':
            db.add(MessageThread(tenant_id=UUID(plan['tenant_id']),customer_id=UUID(plan['customer_id']),customer_phone=TEST_RECIPIENT))
        if change=='foreign_sender':
            # Different literal spelling defeats only a raw-string unique index;
            # normalized ownership must still reject the second shop.
            foreign=Tenant(name='Foreign synthetic',slug='foreign-pilot-'+uuid4().hex,sms_enabled=True,messaging_enabled=True,sms_phone_number='(775) 535-8774')
            db.add(foreign)
        customer=await db.get(Customer,UUID(plan['customer_id']))
        if change=='changed_customer':
            customer.phone='+15005550199'
        elif change=='opt_out':
            customer.sms_opt_out=True
        await db.commit()
        reply=SimpleNamespace(sid='SM'+uuid4().hex,account_sid=ACCOUNT,direction='inbound',from_=TEST_RECIPIENT,to=pilot.SENDER,
            body=plan['reply_token'],date_sent=datetime.now(timezone.utc))
        with pytest.raises(RuntimeError):
            await pilot.import_reply(db,plan,reply)
        assert await db.scalar(select(func.count()).select_from(SMSMessage).where(SMSMessage.tenant_id==UUID(plan['tenant_id'])))==0
        if change=='foreign_sender':
            # Clean only this test's foreign fixture, preserving its history.
            foreign.sms_phone_number=None
            await db.commit()


@pytest.mark.parametrize('campaign_approved', [False, True])
def test_real_provider_owner_gate_precedes_configuration_and_network(monkeypatch, campaign_approved):
    calls=[]
    def forbidden():
        calls.append('configuration')
        raise AssertionError('Must not load configuration while owner gate is held')
    monkeypatch.setattr(pilot,'assert_isolated',forbidden)
    monkeypatch.setattr(pilot,'OWNER_TECHNICAL_TEST_APPROVED',False)
    monkeypatch.setattr(pilot,'LIVE_CAMPAIGN_SCOPE_APPROVED',campaign_approved)
    monkeypatch.setenv('OWNER_TECHNICAL_TEST_APPROVED','true')
    monkeypatch.setenv('LIVE_CAMPAIGN_SCOPE_APPROVED','true')
    monkeypatch.setenv('SMS_PILOT_ENABLED','true')
    with pytest.raises(RuntimeError,match='Owner technical test is not approved'):
        pilot.provider()
    assert calls==[]


@pytest.mark.parametrize('change', ['missing','bad_phone','bad_hash','unknown_field','bad_schema','duplicate_fields','bad_permissions','symlink'])
def test_invalid_private_authorization_fails_before_state_or_provider(monkeypatch, tmp_path, fictional_recipient_runtime, change):
    authorization = fictional_recipient_runtime
    values = {'schema':1,'recipient':TEST_RECIPIENT,'recipient_sha256':pilot.fingerprint(TEST_RECIPIENT)}
    if change=='missing':
        authorization.unlink()
    elif change=='bad_phone':
        authorization.write_text(json.dumps({**values,'recipient':'invalid'}))
    elif change=='bad_hash':
        authorization.write_text(json.dumps({**values,'recipient_sha256':'a'*64}))
    elif change=='unknown_field':
        authorization.write_text(json.dumps({**values,'other':'field'}))
    elif change=='bad_schema':
        authorization.write_text(json.dumps({**values,'schema':True}))
    elif change=='duplicate_fields':
        authorization.write_text('{"schema":1,"schema":1,"recipient":"'+TEST_RECIPIENT+'","recipient_sha256":"'+pilot.fingerprint(TEST_RECIPIENT)+'"}')
    elif change=='bad_permissions':
        authorization.chmod(0o644)
    else:
        link = tmp_path/'linked-authorization.json'
        link.symlink_to(authorization)
        monkeypatch.setattr(pilot,'AUTHORIZATION',link)
    with pytest.raises((RuntimeError,FileNotFoundError)):
        pilot.make_plan(pilot.fingerprint(ACCOUNT))
    assert not (tmp_path/'ledger.sqlite3').exists()


@pytest.mark.asyncio
@pytest.mark.parametrize('fault', ['missing', 'unsafe', 'malformed'])
async def test_prepare_missing_private_authorization_never_reads_state_or_credentials(monkeypatch, fictional_recipient_runtime, fault):
    if fault == 'missing':
        fictional_recipient_runtime.unlink()
    elif fault == 'unsafe':
        fictional_recipient_runtime.chmod(0o644)
    else:
        fictional_recipient_runtime.write_text('{}')
    calls=[]
    def forbidden():
        calls.append(True)
        raise AssertionError('No settings or provider access permitted')
    monkeypatch.setattr(pilot, 'assert_isolated', forbidden)
    monkeypatch.setattr(pilot, 'provider', forbidden)
    with pytest.raises((FileNotFoundError, RuntimeError)):
        await pilot.prepare()
    assert calls == []


def test_environment_cannot_override_private_authorization(monkeypatch):
    other = '+15005550102'
    monkeypatch.setenv('TWILIO_STATUS_PILOT_RECIPIENT', other)
    monkeypatch.setenv('APPROVED_RECIPIENT_SHA256', pilot.fingerprint(other))
    monkeypatch.setenv('TWILIO_STATUS_PILOT_RECIPIENT_SHA256', pilot.fingerprint(other))
    monkeypatch.setenv('TWILIO_STATUS_PILOT_AUTHORIZATION','/tmp/unapproved.json')
    assert pilot.approved_recipient() == TEST_RECIPIENT


def test_changed_private_authorization_cannot_reset_sealed_plan_or_budget(approved,fictional_recipient_runtime):
    plan,ledger=approved
    claim(plan,ledger)
    other='+15005550102'
    fictional_recipient_runtime.write_text(json.dumps({'schema':1,'recipient':other,'recipient_sha256':pilot.fingerprint(other)}))
    with pytest.raises(RuntimeError):
        pilot.validate_plan(plan,ledger)
    with pytest.raises(FileExistsError):
        pilot.initialize_guard(pilot.make_plan(plan['account_hash']),ledger)
    with sqlite3.connect(ledger) as db:
        assert db.execute('SELECT count(*) FROM attempts').fetchone()[0] == 1


def test_private_authorization_requires_current_owner(monkeypatch):
    owner = os.getuid()
    monkeypatch.setattr(pilot.os, 'getuid', lambda: owner+1)
    with pytest.raises(RuntimeError, match='owned private regular file'):
        pilot.approved_recipient()


def test_owner_technical_gate_does_not_claim_campaign_approval():
    assert pilot.OWNER_TECHNICAL_TEST_APPROVED is True
    assert pilot.LIVE_CAMPAIGN_SCOPE_APPROVED is False
    assert pilot.PILOT_PURPOSE == 'owner_only_technical_test'


def test_owner_test_plan_purpose_and_claim_cannot_be_repurposed(approved):
    plan,ledger=approved
    changed=copy.deepcopy(plan)
    changed['purpose']='repair_customer_rollout'
    with pytest.raises(RuntimeError,match='purpose'):
        pilot.claim_provider_call(changed,'work_started_sms',body=plan['events']['work_started_sms']['body'],
            from_number=pilot.SENDER,to_number=TEST_RECIPIENT,account_hash=plan['account_hash'],ledger=ledger)
    with sqlite3.connect(ledger) as db:
        assert db.execute('SELECT count(*) FROM attempts').fetchone()[0] == 0


def test_reviewed_owner_mode_provider_uses_only_explicit_fake_credentials(monkeypatch,tmp_path):
    from app.core.config import settings
    import dotenv
    import twilio.rest
    monkeypatch.setenv('TWILIO_STATUS_PILOT_LOCAL','1')
    monkeypatch.setenv('COMMUNICATIONS_ISOLATED_LOCAL','1')
    monkeypatch.setattr(settings,'DATABASE_URL','postgresql+asyncpg://comms_local:synthetic@127.0.0.1:55460/'+pilot.DATABASE)
    monkeypatch.setattr(settings,'ENVIRONMENT','development')
    monkeypatch.setattr(settings,'TWILIO_ACCOUNT_SID','')
    monkeypatch.setattr(settings,'TWILIO_AUTH_TOKEN','')
    for name in ('SMS_TENANT_ROUTING_ENABLED','SMS_AUTOMATION_OUTBOX_ENABLED','SMS_RECOVERY_ENABLED'):
        monkeypatch.setattr(settings,name,False)
    fake_source=tmp_path/'fake-credentials.env'
    monkeypatch.setattr(pilot,'CREDENTIAL_SOURCE',fake_source)
    reads=[]
    def fake_values(path):
        assert path == fake_source
        reads.append(path)
        return {'TWILIO_ACCOUNT_SID':ACCOUNT,'TWILIO_AUTH_TOKEN':'synthetic-test-token'}
    sentinel=object()
    def fake_client(account,token,**kwargs):
        assert account == ACCOUNT and token == 'synthetic-test-token'
        assert kwargs['http_client'].timeout == 25
        return sentinel
    monkeypatch.setattr(dotenv,'dotenv_values',fake_values)
    monkeypatch.setattr(twilio.rest,'Client',fake_client)
    assert pilot.OWNER_TECHNICAL_TEST_APPROVED is True and pilot.LIVE_CAMPAIGN_SCOPE_APPROVED is False
    client,digest=pilot.provider()
    assert client is sentinel and digest == pilot.fingerprint(ACCOUNT) and reads == [fake_source]
