"""Closed, two-message operator pilot. No API, scheduler or real order mutation.

Run only through the approved isolated process launcher. State is permanent across
worktrees. No reset, recipient, sender, body or credential CLI options exist.
"""
from __future__ import annotations
import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

SENDER = '+17755358774'
EVENTS = ('work_started_sms', 'ready_pickup_sms')
STATE_DIR = Path.home() / '.codex/state/dieselbridge/twilio-status-pilot-20261020'
AUTHORIZATION = STATE_DIR / 'authorization.json'
PLAN = STATE_DIR / 'plan.json'
LEDGER = STATE_DIR / 'ledger.sqlite3'
CREDENTIAL_SOURCE = Path.home() / 'GitHub/truck-pit-stop/backend/.env'
DATABASE = 'twilio_status_pilot_20261020'
# Verified parking registration does not establish approval for customer repair-status traffic.
# Deliberately no environment/CLI override; changing this requires reviewed source.
LIVE_CAMPAIGN_SCOPE_APPROVED = False
# Reviewed authorization covers only this operator's two sealed technical TEST events.
# Campaign approval alone never permits this tool, and no environment/CLI override exists.
OWNER_TECHNICAL_TEST_APPROVED = True
PILOT_PURPOSE = 'owner_only_technical_test'


def fingerprint(value):
    return hashlib.sha256(value.encode()).hexdigest()


def approved_recipient():
    """Read reviewed private authorization; never create it or accept overrides."""
    _private_file(AUTHORIZATION)
    metadata = AUTHORIZATION.stat()
    if stat.S_IMODE(metadata.st_mode) != 0o600 or metadata.st_size > 4096:
        raise RuntimeError('Pilot authorization must be a small private0600 file')
    def unique_object(pairs):
        result = dict(pairs)
        if len(result) != len(pairs):
            raise RuntimeError('Duplicate authorization fields')
        return result
    try:
        authorization = json.loads(AUTHORIZATION.read_text(), object_pairs_hook=unique_object)
    except (ValueError, UnicodeDecodeError):
        raise RuntimeError('Invalid private pilot authorization') from None
    if (not isinstance(authorization, dict) or set(authorization) != {'schema','recipient','recipient_sha256'}
        or type(authorization['schema']) is not int or authorization['schema'] != 1):
        raise RuntimeError('Invalid private pilot authorization schema')
    value, digest = authorization['recipient'], authorization['recipient_sha256']
    if (not isinstance(value, str) or not re.fullmatch(r'\+[1-9]\d{7,14}', value)
        or not isinstance(digest, str) or not re.fullmatch(r'[a-f0-9]{64}', digest) or fingerprint(value) != digest):
        raise RuntimeError('Invalid private pilot recipient authorization')
    return value


def plan_hash(plan):
    return fingerprint(json.dumps(plan, sort_keys=True, separators=(',', ':')))


def bodies(token):
    return {
        'work_started_sms': f'TEST DieselBridge: simulated repair work started. No real repair changed. Reply STOP to opt out. Ref {token}.',
        'ready_pickup_sms': f'TEST DieselBridge: simulated ready for pickup. No real repair changed. Ref {token}.',
    }


def validate_shape(plan, *, now=None, require_unexpired=True):
    expected = {'schema', 'purpose', 'run_id', 'tenant_id', 'customer_id', 'recipient', 'sender', 'account_hash', 'created_at', 'expires_at', 'reply_token', 'events'}
    if not isinstance(plan, dict) or set(plan) != expected or plan['schema'] != 1 or plan.get('purpose') != PILOT_PURPOSE:
        raise RuntimeError('Invalid pilot plan or purpose')
    if plan['recipient'] != approved_recipient() or plan['sender'] != SENDER:
        raise RuntimeError('Pilot phone pair is outside authorization')
    for key in ('run_id', 'tenant_id', 'customer_id'):
        if str(UUID(plan[key])) != plan[key]:
            raise RuntimeError('Invalid pilot identity')
    if not re.fullmatch(r'[a-f0-9]{64}', plan['account_hash']):
        raise RuntimeError('Invalid account binding')
    if not re.fullmatch(r'TPS-PILOT-[A-F0-9]{8}', plan['reply_token']):
        raise RuntimeError('Invalid reply token')
    created = datetime.fromisoformat(plan['created_at'])
    expires = datetime.fromisoformat(plan['expires_at'])
    if not created.tzinfo or not expires.tzinfo or expires - created != timedelta(hours=24):
        raise RuntimeError('Invalid pilot validity window')
    current = now or datetime.now(timezone.utc)
    if created > current + timedelta(minutes=1) or (require_unexpired and current >= expires):
        raise RuntimeError('Pilot plan expired or not yet valid')
    if not isinstance(plan['events'], dict) or set(plan['events']) != set(EVENTS):
        raise RuntimeError('Pilot permits exactly two event slots')
    for event, body in bodies(plan['reply_token']).items():
        if plan['events'][event] != {'body': body, 'domain_event_id': f"twilio-status-pilot:{plan['run_id']}:{event}"}:
            raise RuntimeError('Pilot event or body changed')


def _private_file(path):
    metadata = path.lstat()
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != os.getuid() or stat.S_IMODE(metadata.st_mode) & 0o077:
        raise RuntimeError('Pilot state must be an owned private regular file')


def initialize_guard(plan, ledger=None):
    ledger = LEDGER if ledger is None else ledger
    validate_shape(plan)
    ledger.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    # Exclusive file creation prevents a new plan from resetting an old budget.
    descriptor = os.open(ledger, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(descriptor)
    with sqlite3.connect(ledger) as connection:
        connection.execute('CREATE TABLE approved(slot INTEGER PRIMARY KEY CHECK(slot=1), binding TEXT NOT NULL)')
        connection.execute('CREATE TABLE attempts(event TEXT PRIMARY KEY CHECK(event IN (\'work_started_sms\',\'ready_pickup_sms\')), binding TEXT NOT NULL)')
        connection.execute('CREATE TABLE receipts(event TEXT PRIMARY KEY, sid TEXT UNIQUE NOT NULL)')
        connection.execute('INSERT INTO approved VALUES(1,?)', (plan_hash(plan),))


def validate_plan(plan, ledger=None, *, require_unexpired=True):
    ledger = LEDGER if ledger is None else ledger
    validate_shape(plan, require_unexpired=require_unexpired)
    _private_file(ledger)
    with sqlite3.connect(ledger) as connection:
        approved = connection.execute('SELECT binding FROM approved WHERE slot=1').fetchone()
        amendment_table = connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='ready_copy_amendments'").fetchone()
        if amendment_table and connection.execute("SELECT 1 FROM ready_copy_amendments WHERE state != 'complete'").fetchone():
            raise RuntimeError('Partial ready-copy amendment requires review; provider access held')
    if not approved or approved[0] != plan_hash(plan):
        raise RuntimeError('Pilot plan changed; provider access refused')


def claim_provider_call(plan, event, *, body, from_number, to_number, account_hash, ledger=None):
    ledger = LEDGER if ledger is None else ledger
    validate_plan(plan, ledger)
    if event not in EVENTS or (body, from_number, to_number, account_hash) != (
        plan['events'][event]['body'], SENDER, approved_recipient(), plan['account_hash']):
        raise RuntimeError('Pilot payload is outside authorization')
    with sqlite3.connect(ledger) as connection:
        connection.execute('BEGIN IMMEDIATE')
        approved = connection.execute('SELECT binding FROM approved WHERE slot=1').fetchone()
        if not approved or approved[0] != plan_hash(plan):
            raise RuntimeError('Pilot plan changed')
        connection.execute('INSERT INTO attempts(event,binding) VALUES(?,?)', (event, plan_hash(plan)))
    # Commit precedes provider I/O. No exception can restore this budget.


def assert_isolated():
    from app.core.config import settings
    from sqlalchemy.engine import make_url
    url = make_url(settings.DATABASE_URL)
    if (os.getenv('TWILIO_STATUS_PILOT_LOCAL') != '1' or os.getenv('COMMUNICATIONS_ISOLATED_LOCAL') != '1'
        or settings.ENVIRONMENT != 'development'
        or (url.host, url.port, url.database, url.username) != ('127.0.0.1', 55460, DATABASE, 'comms_local')):
        raise RuntimeError('Dedicated isolated pilot database required')
    local_token = os.getenv('LOCAL_WEBHOOK_SECRET', '')
    if (settings.TWILIO_AUTH_TOKEN and (not local_token or settings.TWILIO_AUTH_TOKEN != local_token)):
        raise RuntimeError('Normal settings must not contain a live provider token')
    if settings.TWILIO_ACCOUNT_SID or any(getattr(settings, name) for name in (
        'SMS_TENANT_ROUTING_ENABLED', 'SMS_AUTOMATION_OUTBOX_ENABLED', 'SMS_RECOVERY_ENABLED')):
        raise RuntimeError('Live server credentials or enabled rollout flags prohibited')


def provider():
    """Explicit operator-only access: credentials never enter server settings."""
    if OWNER_TECHNICAL_TEST_APPROVED is not True:
        raise RuntimeError('Owner technical test is not approved')
    approved_recipient()
    assert_isolated()
    from dotenv import dotenv_values
    from twilio.http.http_client import TwilioHttpClient
    from twilio.rest import Client
    config = dotenv_values(CREDENTIAL_SOURCE)
    account, token = config.get('TWILIO_ACCOUNT_SID'), config.get('TWILIO_AUTH_TOKEN')
    if not account or not token:
        raise RuntimeError('Existing Twilio account configuration unavailable')
    return Client(account, token, http_client=TwilioHttpClient(timeout=25, max_retries=0)), fingerprint(account)


def make_plan(account_hash):
    created = datetime.now(timezone.utc)
    run_id = str(uuid4())
    token = 'TPS-PILOT-' + uuid4().hex[:8].upper()
    return dict(schema=1, purpose=PILOT_PURPOSE, run_id=run_id, tenant_id=str(uuid4()), customer_id=str(uuid4()),
        recipient=approved_recipient(), sender=SENDER, account_hash=account_hash, created_at=created.isoformat(),
        expires_at=(created + timedelta(hours=24)).isoformat(), reply_token=token,
        events={event: dict(body=body, domain_event_id=f'twilio-status-pilot:{run_id}:{event}') for event, body in bodies(token).items()})


async def prepare():
    approved_recipient()
    assert_isolated()
    if PLAN.exists() or LEDGER.exists():
        raise RuntimeError('Pilot state already exists; budget cannot be recreated')
    approved_recipient()  # Revalidate immediately before any credential/provider access.
    client, account_hash = provider()
    numbers = await asyncio.to_thread(client.incoming_phone_numbers.list, phone_number=SENDER, limit=2)
    if len(numbers) != 1 or numbers[0].phone_number != SENDER or not numbers[0].capabilities.get('sms'):
        raise RuntimeError('Approved sender is not uniquely owned and SMS capable')
    plan = make_plan(account_hash)
    initialize_guard(plan)
    descriptor = os.open(PLAN, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(descriptor, 'w') as file:
        json.dump(plan, file, sort_keys=True)
    from app.db.session import AsyncSessionLocal
    from app.db.models.tenant import Tenant
    from app.db.models.customer import Customer
    async with AsyncSessionLocal() as db:
        db.add(Tenant(id=UUID(plan['tenant_id']), name='Closed status pilot (synthetic)', slug='status-pilot-'+plan['run_id'],
            sms_phone_number=SENDER, sms_enabled=True, messaging_enabled=True))
        await db.flush()
        db.add(Customer(id=UUID(plan['customer_id']), tenant_id=UUID(plan['tenant_id']), first_name='Approved', last_name='Pilot recipient',
            phone=approved_recipient(), email=plan['run_id']+'@pilot.example.test'))
        await db.commit()
    print('Prepared two test slots; no SMS sent. Reply token:', plan['reply_token'])


def validate_receipt(plan, event, receipt, *, expected_sid=None):
    if event not in EVENTS:
        raise RuntimeError('Unknown pilot event')
    if (not receipt.sid or not re.fullmatch(r'SM[a-fA-F0-9]{32}', receipt.sid)
        or (expected_sid is not None and receipt.sid != expected_sid)
        or fingerprint(receipt.account_sid) != plan['account_hash']
        or (receipt.from_, receipt.to, receipt.body) != (SENDER, approved_recipient(), plan['events'][event]['body'])):
        raise RuntimeError('Provider receipt does not match the pilot')


async def local_identity(db, plan, *, require_thread=False):
    """Pin isolated receipt writes to the immutable tenant/customer/thread only."""
    from sqlalchemy import select
    from app.db.models.tenant import Tenant
    from app.db.models.customer import Customer
    from app.db.models.message_thread import MessageThread
    from app.services.messaging_service import _normalize_for_twilio
    tenant_id, customer_id = UUID(plan['tenant_id']), UUID(plan['customer_id'])
    candidates = (await db.scalars(select(Tenant).where(Tenant.sms_enabled.is_(True), Tenant.sms_phone_number.is_not(None)))).all()
    owners = [row for row in candidates if _normalize_for_twilio(row.sms_phone_number) == SENDER]
    if len(owners) != 1 or owners[0].id != tenant_id:
        raise RuntimeError('Pilot sender does not have its unique planned tenant')
    tenant = await db.scalar(select(Tenant).where(Tenant.id == tenant_id).with_for_update().execution_options(populate_existing=True))
    if not tenant or not tenant.is_active or tenant.deleted_at or not tenant.sms_enabled or not tenant.messaging_enabled or tenant.sms_phone_number != SENDER:
        raise RuntimeError('Pilot tenant changed')
    customers = (await db.scalars(select(Customer).where(Customer.tenant_id == tenant_id, Customer.deleted_at.is_(None)))).all()
    recipients = [row for row in customers if _normalize_for_twilio(row.phone or '') == approved_recipient()]
    if len(recipients) != 1 or recipients[0].id != customer_id:
        raise RuntimeError('Pilot recipient does not have its unique planned identity')
    customer = await db.scalar(select(Customer).where(Customer.id == customer_id).with_for_update().execution_options(populate_existing=True))
    if not customer or customer.sms_opt_out or customer.deleted_at or _normalize_for_twilio(customer.phone) != approved_recipient():
        raise RuntimeError('Pilot recipient changed or revoked consent')
    thread = await db.scalar(select(MessageThread).where(MessageThread.tenant_id == tenant_id,
        MessageThread.customer_id == customer_id, MessageThread.deleted_at.is_(None)).with_for_update().execution_options(populate_existing=True))
    if require_thread and (not thread or thread.thread_kind != 'customer' or thread.inquiry_binding_id is not None):
        raise RuntimeError('Pilot conversation is unavailable')
    return tenant, customer, thread


async def import_reply(db, plan, reply):
    """No global customer lookup or creation; only the already planned conversation."""
    assert_isolated()
    validate_plan(plan, require_unexpired=False)
    if not valid_reply(plan, reply):
        raise RuntimeError('Reply is outside the approved pilot')
    from sqlalchemy import select, text
    from app.db.models.sms_message import SMSMessage, SMSMessageDirection, SMSMessageSource, SMSDeliveryStatus
    from app.db.models.communication import ConversationWorkflow
    lock_key = int.from_bytes(hashlib.sha256(('twilio-status-pilot:'+reply.sid).encode()).digest()[:8], 'big', signed=True)
    await db.execute(text('SELECT pg_advisory_xact_lock(:key)'), {'key':lock_key})
    tenant, customer, thread = await local_identity(db, plan, require_thread=True)
    existing = await db.scalar(select(SMSMessage).where(SMSMessage.twilio_message_sid == reply.sid, SMSMessage.twilio_account_sid.is_(None)))
    if existing:
        if (existing.tenant_id, existing.thread_id, existing.customer_id, existing.body, existing.from_number, existing.to_number) != (
            tenant.id, thread.id, customer.id, reply.body, approved_recipient(), SENDER):
            raise RuntimeError('Reply receipt belongs to another conversation')
        return existing.id, True
    message = SMSMessage(tenant_id=tenant.id, thread_id=thread.id, customer_id=customer.id,
        direction=SMSMessageDirection.INBOUND, source=SMSMessageSource.INBOUND, body=reply.body,
        from_number=approved_recipient(), to_number=SENDER, twilio_message_sid=reply.sid,
        delivery_status=SMSDeliveryStatus.DELIVERED, created_at=reply.date_sent, sent_at=reply.date_sent, delivered_at=reply.date_sent)
    db.add(message)
    if not thread.last_message_at or reply.date_sent >= thread.last_message_at:
        thread.last_message_at, thread.last_message_preview = reply.date_sent, reply.body[:240]
    thread.unread_count_staff = (thread.unread_count_staff or 0) + 1
    workflow = await db.scalar(select(ConversationWorkflow).where(ConversationWorkflow.tenant_id == tenant.id, ConversationWorkflow.thread_id == thread.id))
    if workflow:
        workflow.status = 'open'
        workflow.version += 1
    else:
        db.add(ConversationWorkflow(tenant_id=tenant.id, thread_id=thread.id, status='open', version=2))
    await db.flush()
    return message.id, False


async def send(plan, event):
    assert_isolated()
    validate_plan(plan)
    if event not in EVENTS:
        raise RuntimeError('Unsupported pilot event')
    client, account_hash = provider()
    if account_hash != plan['account_hash']:
        raise RuntimeError('Configured account changed')
    from app.db.session import AsyncSessionLocal
    from app.services import communications_service as manual
    from app.services.automated_sms_service import enqueue_automated_sms, dispatch_automated_operation
    # This process only. No web/worker configuration is changed.
    manual._get_twilio_client = lambda: client
    class GuardedSender(manual.LiveSMSSender):
        async def send(self, *, body, from_number, to_number, status_callback, routing_context=None):
            assert_isolated()
            if routing_context is not None:
                raise RuntimeError('Live pilot permits only the verified legacy transport')
            claim_provider_call(plan, event, body=body, from_number=from_number, to_number=to_number, account_hash=account_hash)
            receipt = await asyncio.wait_for(asyncio.to_thread(client.messages.create,
                body=body, from_=from_number, to=to_number), timeout=30)
            validate_receipt(plan, event, receipt)
            with sqlite3.connect(LEDGER) as connection:
                connection.execute('INSERT INTO receipts(event,sid) VALUES(?,?)', (event, receipt.sid))
            return {'sid': receipt.sid, 'status': receipt.status}
    async with AsyncSessionLocal() as db:
        await local_identity(db, plan)
        operation = await enqueue_automated_sms(db, tenant_id=UUID(plan['tenant_id']),
            domain_event_id=plan['events'][event]['domain_event_id'], template_name=event,
            to=approved_recipient(), body=plan['events'][event]['body'], customer_id=UUID(plan['customer_id']))
        await db.commit()
        operation_id = operation.id
    async with AsyncSessionLocal() as db:
        await dispatch_automated_operation(db, operation_id, GuardedSender())
    # Same committed event and dispatch replay must consume no additional budget.
    async with AsyncSessionLocal() as db:
        replay = await enqueue_automated_sms(db, tenant_id=UUID(plan['tenant_id']),
            domain_event_id=plan['events'][event]['domain_event_id'], template_name=event,
            to=approved_recipient(), body=plan['events'][event]['body'], customer_id=UUID(plan['customer_id']))
        if replay.id != operation_id:
            raise RuntimeError('Pilot event replay did not reuse the operation')
        await db.commit()
        await dispatch_automated_operation(db, operation_id, GuardedSender())
    print('Pilot event processed:', event, 'operation:', operation_id, '(delivery/reply require status checks)')


def valid_reply(plan, reply):
    created = datetime.fromisoformat(plan['created_at'])
    expires = datetime.fromisoformat(plan['expires_at'])
    sent = getattr(reply, 'date_sent', None)
    return bool(isinstance(getattr(reply, 'sid', None), str)
        and re.fullmatch(r'SM[a-fA-F0-9]{32}', reply.sid)
        and reply.direction == 'inbound' and isinstance(reply.account_sid, str)
        and fingerprint(reply.account_sid) == plan['account_hash']
        and reply.from_ == approved_recipient() and reply.to == SENDER
        and isinstance(reply.body, str) and reply.body.strip() == plan['reply_token']
        and isinstance(sent, datetime) and sent.tzinfo is not None and created <= sent <= expires)


async def status(plan):
    assert_isolated()
    validate_plan(plan, require_unexpired=False)  # Read-only reconciliation survives expiry.
    client, account_hash = provider()
    if account_hash != plan['account_hash']:
        raise RuntimeError('Configured account changed')
    from sqlalchemy import select
    from app.db.session import AsyncSessionLocal
    from app.db.models.automated_sms import AutomatedSMSOperation
    from app.services.messaging_service import process_twilio_status_callback
    for event in EVENTS:
        async with AsyncSessionLocal() as db:
            await local_identity(db, plan)
            operation = await db.scalar(select(AutomatedSMSOperation).where(AutomatedSMSOperation.tenant_id == UUID(plan['tenant_id']),
                AutomatedSMSOperation.domain_event_id == plan['events'][event]['domain_event_id']))
            if not operation or not operation.provider_message_sid:
                print(event, 'no confirmed receipt; never resend an uncertain event')
                continue
            receipt = await asyncio.to_thread(client.messages(operation.provider_message_sid).fetch)
            validate_receipt(plan, event, receipt, expected_sid=operation.provider_message_sid)
            with sqlite3.connect(LEDGER) as connection:
                stored = connection.execute('SELECT sid FROM receipts WHERE event=?', (event,)).fetchone()
            if not stored or stored[0] != receipt.sid:
                raise RuntimeError('Receipt lacks a permanent pilot claim')
            await process_twilio_status_callback(db, message_sid=receipt.sid, message_status=receipt.status,
                error_code=str(receipt.error_code) if receipt.error_code else None)
            print(event, 'provider status:', receipt.status, 'error code:', receipt.error_code)
    print('Outbound-only status check complete; no SMS reply is requested or polled.')


async def main():
    approved_recipient()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('prepare', 'send', 'status'))
    parser.add_argument('--event', choices=EVENTS)
    args = parser.parse_args()
    assert_isolated()
    if args.command == 'prepare':
        if args.event:
            raise RuntimeError('Prepare accepts no event override')
        await prepare()
        return
    _private_file(PLAN)
    plan = json.loads(PLAN.read_text())
    if args.command == 'send':
        if not args.event:
            raise RuntimeError('Choose one of the two approved event slots')
        await send(plan, args.event)
    else:
        if args.event:
            raise RuntimeError('Status checks both immutable event slots')
        await status(plan)


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except Exception as error:
        # SDK and DB exceptions can contain credentials or private request data.
        print('Pilot stopped:', type(error).__name__, 'provider code:', getattr(error, 'code', None))
        raise SystemExit(1)
