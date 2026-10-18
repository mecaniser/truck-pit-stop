"""One-recipient, one-provider-call acceptance. Never a server or recovery worker.

Run through communications_local.py exec. Credentials are read in memory from
an existing configuration file, never copied into this checkout. Provider status
and exact nonce replies are polled; this does not certify public webhook delivery.
"""
import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
from datetime import datetime, timezone
from uuid import UUID, uuid4

ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / '.env.sms-acceptance.local'
LEDGER = ROOT / '.sms-acceptance.sqlite'
APPROVED_RECIPIENT_SHA256 = 'c7448088b44683c8f3866cf3c66bae362dbacc709ea02bdbe43a143e98326efa'
SOURCE = Path('/Users/sergio_m1_promax/GitHub/truck-pit-stop/backend/.env')


def binding(plan):
    return hashlib.sha256(json.dumps(plan, sort_keys=True).encode()).hexdigest()


def assert_approved_recipient(recipient):
    if hashlib.sha256((recipient or '').encode()).hexdigest() != APPROVED_RECIPIENT_SHA256:
        raise RuntimeError('Recipient is outside user authorization')


def validate_plan(plan, ledger=LEDGER):
    assert_approved_recipient(plan['recipient'])
    with sqlite3.connect(ledger) as conn:
        approved = conn.execute('SELECT binding FROM approved WHERE slot=1').fetchone()
        if not approved or approved[0] != binding(plan):
            raise RuntimeError('Acceptance plan changed; refusing provider access')


def initialize_guard(plan, ledger=LEDGER):
    assert_approved_recipient(plan['recipient'])
    with sqlite3.connect(ledger) as conn:
        conn.execute('CREATE TABLE IF NOT EXISTS approved (slot INTEGER PRIMARY KEY CHECK(slot=1), binding TEXT NOT NULL)')
        conn.execute('CREATE TABLE IF NOT EXISTS attempts (slot INTEGER PRIMARY KEY CHECK(slot=1), binding TEXT NOT NULL)')
        conn.execute('INSERT INTO approved VALUES (1, ?)', (binding(plan),))
    ledger.chmod(0o600)


def claim_provider_call(plan, *, body, from_number, to_number, ledger=LEDGER):
    validate_plan(plan, ledger)
    if (to_number, from_number, body) != (plan['recipient'], plan['sender'], plan['body']):
        raise RuntimeError('Acceptance payload is outside the approved recipient/sender/body')
    with sqlite3.connect(ledger) as conn:
        conn.execute('BEGIN IMMEDIATE')
        approved = conn.execute('SELECT binding FROM approved WHERE slot=1').fetchone()
        if not approved or approved[0] != binding(plan):
            raise RuntimeError('Acceptance plan changed; refusing provider access')
        # Commit before I/O. A crash or timeout consumes the budget permanently.
        conn.execute('INSERT INTO attempts VALUES (1, ?)', (binding(plan),))


def assert_isolated():
    from app.core.config import settings
    from sqlalchemy.engine import make_url
    url = make_url(settings.DATABASE_URL)
    if os.environ.get('COMMUNICATIONS_ISOLATED_LOCAL') != '1' or settings.ENVIRONMENT != 'development' or (url.host, url.port, url.database, url.username) != ('127.0.0.1', 55460, 'communications_local', 'comms_local'):
        raise RuntimeError('Only the dedicated local communications database is permitted')
    if settings.TWILIO_ACCOUNT_SID or settings.SMS_RECOVERY_ENABLED:
        raise RuntimeError('Live server credentials or scheduled recovery are prohibited')


def provider():
    from dotenv import dotenv_values
    from twilio.rest import Client
    from twilio.http.http_client import TwilioHttpClient
    config = dotenv_values(SOURCE)
    if not all(config.get(k) for k in ('TWILIO_ACCOUNT_SID', 'TWILIO_AUTH_TOKEN', 'TWILIO_PHONE_NUMBER')):
        raise RuntimeError('Existing Twilio configuration is incomplete')
    client = Client(config['TWILIO_ACCOUNT_SID'], config['TWILIO_AUTH_TOKEN'], http_client=TwilioHttpClient(timeout=25, max_retries=0))
    return client, config['TWILIO_PHONE_NUMBER']


async def prepare(recipient):
    assert_approved_recipient(recipient)
    if PLAN.exists() or LEDGER.exists():
        raise RuntimeError('A test plan already exists; use send/status without recreating it')
    if not re.fullmatch(r'\+[1-9]\d{7,14}', recipient or ''):
        raise RuntimeError('An explicit approved E.164 recipient is required')
    client, sender = provider()
    numbers = client.incoming_phone_numbers.list(phone_number=sender, limit=2)
    if len(numbers) != 1 or not numbers[0].capabilities.get('sms'):
        raise RuntimeError('Configured sender is not uniquely SMS capable')
    nonce = 'DB' + uuid4().hex[:8].upper()
    plan = dict(recipient=recipient, sender=sender, tenant_id=str(uuid4()), customer_id=str(uuid4()), event='live-acceptance:' + str(uuid4()), nonce=nonce, created_at=datetime.now(timezone.utc).isoformat(), body=f'DieselBridge SMS test {nonce}. Please reply {nonce} to confirm. This is a test; no service request.')
    with PLAN.open('x') as file:
        os.chmod(PLAN, 0o600)
        json.dump(plan, file)
    initialize_guard(plan)
    from app.db.session import AsyncSessionLocal
    from app.db.models.tenant import Tenant
    from app.db.models.customer import Customer
    async with AsyncSessionLocal() as db:
        db.add(Tenant(id=UUID(plan['tenant_id']), name='Real SMS acceptance (local only)', slug='sms-acceptance-' + plan['tenant_id'], sms_phone_number=sender, sms_enabled=True, messaging_enabled=True))
        await db.flush()
        db.add(Customer(id=UUID(plan['customer_id']), tenant_id=UUID(plan['tenant_id']), first_name='Authorized', last_name='SMS tester', phone=recipient, email='sms-acceptance@communications.example.com'))
        await db.commit()
    print('Prepared one-recipient test; no SMS sent. Reply token:', nonce)


async def send(plan):
    validate_plan(plan)
    from app.db.session import AsyncSessionLocal
    from app.services import communications_service as manual
    from app.services.automated_sms_service import enqueue_automated_sms, dispatch_automated_operation
    client, sender = provider()
    if sender != plan['sender']:
        raise RuntimeError('Configured sender changed')
    manual._get_twilio_client = lambda: client  # Process-local, no API/worker configuration changes.
    class GuardedSender(manual.LiveSMSSender):
        async def send(self, *, body, from_number, to_number, status_callback):
            claim_provider_call(plan, body=body, from_number=from_number, to_number=to_number)
            # There is no public test webhook. Do not submit a localhost callback
            # or change production routing; exact receipt polling is explicit.
            return await super().send(body=body, from_number=from_number, to_number=to_number, status_callback=None)
    async with AsyncSessionLocal() as db:
        operation = await enqueue_automated_sms(db, tenant_id=UUID(plan['tenant_id']), domain_event_id=plan['event'], template_name='work_started_sms', to=plan['recipient'], body=plan['body'], customer_id=UUID(plan['customer_id']))
        await db.commit()
        operation_id = operation.id
    async with AsyncSessionLocal() as db:
        await dispatch_automated_operation(db, operation_id, GuardedSender())
    # Replaying the identical committed event must reuse the operation, and
    # dispatching it again must return without crossing the provider boundary.
    async with AsyncSessionLocal() as db:
        replay = await enqueue_automated_sms(db, tenant_id=UUID(plan['tenant_id']), domain_event_id=plan['event'], template_name='work_started_sms', to=plan['recipient'], body=plan['body'], customer_id=UUID(plan['customer_id']))
        assert replay.id == operation_id
        await db.commit()
        await dispatch_automated_operation(db, operation_id, GuardedSender())
    await status(plan)


async def status(plan):
    validate_plan(plan)
    from sqlalchemy import select
    from app.db.session import AsyncSessionLocal
    from app.db.models.automated_sms import AutomatedSMSOperation
    from app.services.messaging_service import process_twilio_status_callback, handle_inbound_sms
    client, sender = provider()
    if sender != plan['sender']:
        raise RuntimeError('Configured sender changed')
    async with AsyncSessionLocal() as db:
        operation = await db.scalar(select(AutomatedSMSOperation).where(AutomatedSMSOperation.tenant_id == UUID(plan['tenant_id']), AutomatedSMSOperation.domain_event_id == plan['event']))
        if not operation:
            print('Prepared; no send operation yet.')
            return
        print('Operation:', operation.state, 'attempts:', operation.attempt_count)
        if not operation.provider_message_sid:
            print('No provider receipt; do not resend automatically.')
            return
        message = client.messages(operation.provider_message_sid).fetch()
        if (message.to, message.from_, message.body) != (plan['recipient'], plan['sender'], plan['body']):
            raise RuntimeError('Provider receipt does not match the test')
        print('Provider status:', message.status, 'error code:', message.error_code)
        # Explicit authenticated provider polling, not a signed-webhook claim.
        await process_twilio_status_callback(db, message_sid=message.sid, message_status=message.status, error_code=str(message.error_code) if message.error_code else None)
    replies = client.messages.list(from_=plan['recipient'], to=plan['sender'], date_sent_after=datetime.fromisoformat(plan['created_at']), limit=10)
    for reply in replies:
        if reply.direction == 'inbound' and reply.body.strip() == plan['nonce']:
            async with AsyncSessionLocal() as db:
                await handle_inbound_sms(db, to_number=plan['sender'], from_number=plan['recipient'], body=reply.body, twilio_message_sid=reply.sid)
            print('Exact test reply received and imported to isolated inbox. Reply token:', plan['nonce'])
            return
    print('Awaiting exact test reply:', plan['nonce'])


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('prepare', 'send', 'status'))
    parser.add_argument('--recipient')
    args = parser.parse_args()
    assert_isolated()
    if args.command == 'prepare':
        await prepare(args.recipient)
    else:
        await (send if args.command == 'send' else status)(json.loads(PLAN.read_text()))

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except Exception as error:
        # SDK/DB errors can carry credentials, bodies or phone numbers. Fail
        # without printing raw exception/traceback; investigate locally masked.
        print('Acceptance stopped:', type(error).__name__, 'provider code:', getattr(error, 'code', None))
        raise SystemExit(1)
