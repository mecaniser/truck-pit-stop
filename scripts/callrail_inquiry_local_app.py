"""Guarded CallRail HTTP simulator for isolated, signed-in inbox acceptance.

No public control route or production import. The real adapter parses a synthetic
200/201 response through its normal scope validation and durable send operation.
"""
import hashlib
import json
import os
from pathlib import Path
import sqlite3
from types import SimpleNamespace
from uuid import uuid4

import httpx
from sqlalchemy import select
from communications_local_app import app  # enforces isolated DB and denies real Twilio
from app.db.session import AsyncSessionLocal
from app.db.models.callrail import CallRailNumberBinding
from app.services import callrail_service

if any(os.environ.get(name) not in ('', 'false', None) for name in (
    'SMS_TENANT_ROUTING_ENABLED', 'SMS_AUTOMATION_OUTBOX_ENABLED', 'SMS_RECOVERY_ENABLED')):
    raise RuntimeError('All new SMS flags must remain off in the CallRail sandbox')
if any(key.startswith('CALLRAIL_') and key not in {'CALLRAIL_LOCAL_API', 'CALLRAIL_LOCAL_SIGNING'}
       for key in os.environ):
    raise RuntimeError('Unexpected provider credential reference in local sandbox')
os.environ['CALLRAIL_LOCAL_API'] = 'synthetic-local-key-not-a-provider-credential'
os.environ['CALLRAIL_LOCAL_SIGNING'] = os.environ['LOCAL_WEBHOOK_SECRET']
status = int(os.environ.get('LOCAL_CALLRAIL_HTTP_STATUS', '200'))
if status not in {200, 201}:
    raise RuntimeError('Use unit tests for ambiguous provider outcomes')
ledger_path = Path(__file__).resolve().parents[1] / '.communications-provider.sqlite'
original_client = httpx.AsyncClient


async def respond(request):
    if (request.method != 'POST' or request.url.host != 'api.callrail.com'
        or request.url.path != '/v3/a/ACCsynthetic/text-messages.json'):
        raise RuntimeError('Non-synthetic provider request prohibited')
    payload = json.loads(request.content)
    if (payload.get('company_id') != 'COMsynthetic'
        or not isinstance(payload.get('content'), str)
        or not 0 < len(payload['content']) <= 140):
        raise RuntimeError('Invalid synthetic request')
    async with AsyncSessionLocal() as db:
        binding = await db.scalar(select(CallRailNumberBinding).where(
            CallRailNumberBinding.account_id == 'ACCsynthetic',
            CallRailNumberBinding.company_id == 'COMsynthetic',
            CallRailNumberBinding.sender_phone == payload.get('tracking_number'),
            CallRailNumberBinding.credential_ref == 'CALLRAIL_LOCAL_API',
            CallRailNumberBinding.enabled.is_(True),
            CallRailNumberBinding.deleted_at.is_(None)))
        if binding is None:
            raise RuntimeError('Synthetic number not explicitly configured')
        tracker = binding.tracker_id
    identifier = 'local' + hashlib.sha256(
        (payload['tracking_number'] + ':' + payload['customer_phone_number']).encode()).hexdigest()[:24]
    with sqlite3.connect(ledger_path) as ledger:
        ledger.execute('CREATE TABLE IF NOT EXISTS callrail_http_calls '
                       '(id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL, status INTEGER NOT NULL)')
        ledger.execute('INSERT INTO callrail_http_calls VALUES (?,?,?)', (str(uuid4()), identifier, status))
    return httpx.Response(status, json={
        'id': identifier, 'company_id': 'COMsynthetic',
        'customer_phone_number': payload['customer_phone_number'],
        'current_tracking_number': payload['tracking_number'],
        'current_tracker_id': tracker,
    })


def client(**kwargs):
    return original_client(transport=httpx.MockTransport(respond), **kwargs)


# Replace this adapter's module reference only, leaving unrelated HTTP clients intact.
callrail_service.httpx = SimpleNamespace(AsyncClient=client)
