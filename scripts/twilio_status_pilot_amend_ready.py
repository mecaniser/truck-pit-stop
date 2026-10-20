"""One-time correction of the unused ready-pickup TEST copy; no provider access.

Fixed private state only. Never recreates a plan, ledger or budget. A partial
failure deliberately leaves a mismatch requiring review, never an automatic retry.
"""
from __future__ import annotations
import asyncio
import copy
from datetime import datetime, timezone
import json
import os
import sqlite3
import twilio_status_pilot as pilot

MARKER = 'unused_ready_copy_no_reply'
REASON = 'Owner requested outbound-only TEST copy; unused second slot only.'


def amended_plan(old):
    new = copy.deepcopy(old)
    if not isinstance(old, dict) or not isinstance(old.get('events'), dict):
        raise RuntimeError('Unexpected private pilot plan shape')
    token = old.get('reply_token')
    legacy = f'TEST DieselBridge: simulated ready for pickup. No real repair changed. Please reply {token}.'
    if old['events'].get('ready_pickup_sms', {}).get('body') != legacy:
        raise RuntimeError('Only the exact unused reply-request copy may be amended once')
    new['events']['ready_pickup_sms']['body'] = pilot.bodies(token)['ready_pickup_sms']
    # Prove every other field is identical and valid under current sealed source.
    pilot.validate_shape(new)
    return new


def check_ledger(connection, old, new):
    old_hash, new_hash = pilot.plan_hash(old), pilot.plan_hash(new)
    approved = connection.execute('SELECT binding FROM approved WHERE slot=1').fetchone()
    if not approved or approved[0] != old_hash:
        raise RuntimeError('Global plan approval does not match the old immutable plan')
    marker = connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='ready_copy_amendments'").fetchone()
    if marker and connection.execute('SELECT 1 FROM ready_copy_amendments').fetchone():
        raise RuntimeError('Ready-copy amendment is already consumed or incomplete')
    claims = connection.execute('SELECT event,binding FROM attempts').fetchall()
    receipts = connection.execute('SELECT event,sid FROM receipts').fetchall()
    if claims != [('work_started_sms', old_hash)] or len(receipts) != 1 or receipts[0][0] != 'work_started_sms':
        raise RuntimeError('Exactly the first event claim and receipt must exist; second slot must be untouched')
    if not isinstance(receipts[0][1],str) or not pilot.re.fullmatch(r'SM[a-fA-F0-9]{32}',receipts[0][1]):
        raise RuntimeError('First receipt SID is malformed')
    return old_hash, new_hash, receipts[0][1]


async def check_database(db, old, first_sid):
    from sqlalchemy import select, text
    from app.db.models.automated_sms import AutomatedSMSOperation
    from app.db.models.sms_message import SMSMessage, SMSDeliveryStatus, SMSMessageSource, SMSMessageDirection
    tenant, customer, thread = await pilot.local_identity(db, old, require_thread=True)
    # enqueue_automated_sms holds this same customer lock before its event key.
    # Taking its stable key too blocks a competing enqueue until all checks finish.
    from app.services.automated_sms_service import digest
    key = digest([old['tenant_id'], old['events']['ready_pickup_sms']['domain_event_id'],
                  'ready_pickup_sms', '1', 'customer', old['customer_id']])
    await db.execute(text('SELECT pg_advisory_xact_lock(:key)'), {'key':int.from_bytes(bytes.fromhex(key)[:8], 'big', signed=True)})
    second = await db.scalar(select(AutomatedSMSOperation.id).where(
        AutomatedSMSOperation.tenant_id == tenant.id,
        AutomatedSMSOperation.domain_event_id == old['events']['ready_pickup_sms']['domain_event_id']))
    if second:
        raise RuntimeError('Second database operation already exists; amendment refused')
    first = await db.scalar(select(AutomatedSMSOperation).where(
        AutomatedSMSOperation.tenant_id == tenant.id,
        AutomatedSMSOperation.domain_event_id == old['events']['work_started_sms']['domain_event_id']).with_for_update())
    if (not first or first.state != 'accepted' or first.attempt_count != 1 or first.delivery_status != 'delivered'
        or first.binding_id is not None or first.twilio_account_sid is not None or first.messaging_service_sid is not None
        or first.payload_hash != digest([old['sender'],old['recipient'],old['events']['work_started_sms']['body']])
        or first.template_name != 'work_started_sms' or first.template_version != '1' or first.recipient_kind != 'customer'
        or first.recipient_id != customer.id or first.provider_message_sid != first_sid
        or first.body != old['events']['work_started_sms']['body']
        or (first.from_number, first.to_number) != (old['sender'], old['recipient'])):
        raise RuntimeError('First database operation does not prove the delivered authorized attempt')
    message = await db.scalar(select(SMSMessage).where(SMSMessage.id == first.message_id, SMSMessage.tenant_id == tenant.id))
    if (not message or message.thread_id != thread.id or message.customer_id != customer.id
        or message.direction != SMSMessageDirection.OUTBOUND or message.source != SMSMessageSource.AUTOMATED or message.delivery_status != SMSDeliveryStatus.DELIVERED
        or message.twilio_message_sid != first_sid or message.body != first.body
        or (message.from_number, message.to_number) != (old['sender'], old['recipient'])):
        raise RuntimeError('First message receipt does not match the planned conversation')
    return first.id


async def amend_ready_copy():
    if pilot.OWNER_TECHNICAL_TEST_APPROVED is not True or pilot.PILOT_PURPOSE != 'owner_only_technical_test':
        raise RuntimeError('Owner-only technical scope is required')
    pilot.approved_recipient()
    pilot.assert_isolated()
    pilot._private_file(pilot.PLAN)
    pilot._private_file(pilot.LEDGER)
    old = json.loads(pilot.PLAN.read_text())
    new = amended_plan(old)
    temporary = pilot.PLAN.with_name('plan.ready-amendment.tmp')
    if temporary.exists():
        raise RuntimeError('A prior partial amendment requires review')
    from app.db.session import AsyncSessionLocal
    with sqlite3.connect(pilot.LEDGER, timeout=1) as connection:
        connection.execute('BEGIN IMMEDIATE')
        old_hash, new_hash, first_sid = check_ledger(connection, old, new)
        async with AsyncSessionLocal() as db:
            first_operation_id = await check_database(db, old, first_sid)
            # Revalidate all private input after database waits, before mutation.
            pilot._private_file(pilot.PLAN)
            if pilot.plan_hash(json.loads(pilot.PLAN.read_text())) != old_hash:
                raise RuntimeError('Private plan changed during amendment')
            pilot.validate_shape(new)
            descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, 'w') as file:
                json.dump(new, file, sort_keys=True)
                file.flush()
                os.fsync(file.fileno())
            connection.execute('CREATE TABLE IF NOT EXISTS ready_copy_amendments(marker TEXT PRIMARY KEY CHECK(marker=\'unused_ready_copy_no_reply\'),old_hash TEXT NOT NULL,new_hash TEXT NOT NULL,reason TEXT NOT NULL,created_at TEXT NOT NULL,first_operation_id TEXT NOT NULL,state TEXT NOT NULL CHECK(state IN (\'committing\',\'complete\')))')
            connection.execute('INSERT INTO ready_copy_amendments VALUES(?,?,?,?,?,?,?)',
                (MARKER, old_hash, new_hash, REASON, datetime.now(timezone.utc).isoformat(), str(first_operation_id), 'committing'))
            connection.execute('UPDATE approved SET binding=? WHERE slot=1 AND binding=?', (new_hash, old_hash))
            connection.commit()  # Marker/hash first: any later crash leaves sends held.
            os.replace(temporary, pilot.PLAN)
            directory = os.open(pilot.PLAN.parent, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
            connection.execute('BEGIN IMMEDIATE')
            connection.execute("UPDATE ready_copy_amendments SET state='complete' WHERE marker=? AND state='committing'", (MARKER,))
            connection.commit()
            # No PG rows were edited. Release locks only after the new plan is durable.
            await db.rollback()
    pilot.validate_plan(new)
    print('Unused ready-copy amended once. First receipt/budget retained; no provider request made.')


if __name__ == '__main__':
    try:
        asyncio.run(amend_ready_copy())
    except Exception as error:
        print('Amendment stopped:', type(error).__name__, '(review required; never reset or auto-resend)')
        raise SystemExit(1)
