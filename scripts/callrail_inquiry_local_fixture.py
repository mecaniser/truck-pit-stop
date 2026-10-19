"""Explicit synthetic bindings and signed callbacks for the local inbox only."""
import argparse
import asyncio
import base64
from datetime import datetime, timezone
import hashlib
import hmac
import json
import os
import urllib.request
from uuid import UUID, uuid4

from app.core.config import settings
from app.db.models.callrail import CallRailNumberBinding
from app.db.models.message_thread import MessageThread
from app.db.session import AsyncSessionLocal

ANCHOR = UUID('00000000-0000-4000-8000-000000009001')
LINES = {11: UUID('00000000-0000-4000-8000-000000009101'),
         12: UUID('00000000-0000-4000-8000-000000009102')}


def guard():
    if (os.environ.get('COMMUNICATIONS_ISOLATED_LOCAL') != '1'
        or settings.ENVIRONMENT != 'development'
        or '@127.0.0.1:55460/communications_local' not in settings.DATABASE_URL
        or any(getattr(settings, key) for key in (
            'SMS_TENANT_ROUTING_ENABLED', 'SMS_AUTOMATION_OUTBOX_ENABLED', 'SMS_RECOVERY_ENABLED'))):
        raise RuntimeError('Explicit isolated sandbox with all new flags off required')


async def setup():
    async with AsyncSessionLocal() as db:
        thread = await db.get(MessageThread, UUID('00000000-0000-4000-8000-000000001100'))
        anchor = await db.get(CallRailNumberBinding, ANCHOR)
        if (not thread or not anchor or anchor.tenant_id != thread.tenant_id
            or anchor.account_id != 'ACCsynthetic' or anchor.company_id != 'COMsynthetic'
            or anchor.signing_secret_ref != 'CALLRAIL_LOCAL_SIGNING'):
            raise RuntimeError('Expected existing synthetic shop/anchor missing')
        for number, identifier in LINES.items():
            expected = dict(tenant_id=thread.tenant_id, account_id='ACCsynthetic', company_id='COMsynthetic',
                tracker_id='TRKsyntheticPool', sender_phone='+150055500' + str(number),
                credential_ref='CALLRAIL_LOCAL_API', signing_secret_ref='CALLRAIL_LOCAL_SIGNING',
                enabled=True, accept_new_inquiries=True)
            existing = await db.get(CallRailNumberBinding, identifier)
            if existing and any(getattr(existing, key) != value for key, value in expected.items()):
                raise RuntimeError('Existing fixture binding changed; refusing overwrite')
            if not existing:
                db.add(CallRailNumberBinding(id=identifier, **expected))
        await db.commit()
    print('Two explicit synthetic receiving numbers ready; customer/history unchanged')


def event(args):
    local = '+150055500' + str(args.line)
    remote = '+15005550222'
    incoming = args.kind == 'received'
    receipt = args.receipt or 'SCIlocal' + uuid4().hex
    payload = dict(resource_id=receipt, company_resource_id='COMsynthetic',
        account_id='ACCsynthetic', source_number=remote if incoming else local,
        destination_number=local if incoming else remote, content=args.body, message_type='sms',
        timestamp=datetime.now(timezone.utc).isoformat(),
        conversation_id='local' + hashlib.sha256((local + ':' + remote).encode()).hexdigest()[:24])
    raw = json.dumps(payload, separators=(',', ':')).encode()
    signature = base64.b64encode(hmac.new(os.environ['LOCAL_WEBHOOK_SECRET'].encode(), raw, hashlib.sha1).digest()).decode()
    request = urllib.request.Request('http://127.0.0.1:8006/api/v1/webhooks/callrail/' + str(ANCHOR)
        + '/company/' + args.kind, data=raw, headers={'Content-Type': 'application/json', 'Signature': signature}, method='POST')
    with urllib.request.urlopen(request, timeout=10) as response:
        print(json.dumps(dict(receipt=receipt, response=json.load(response))))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['setup', 'event'])
    parser.add_argument('--line', type=int, choices=list(LINES), default=11)
    parser.add_argument('--kind', choices=['received', 'sent'], default='received')
    parser.add_argument('--receipt')
    parser.add_argument('--body', default='New repair inquiry: brake warning light. LOCAL-CR-INQUIRY-A.')
    args = parser.parse_args()
    guard()
    asyncio.run(setup()) if args.command == 'setup' else event(args)
