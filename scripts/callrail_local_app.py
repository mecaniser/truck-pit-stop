"""Explicit synthetic CallRail adapter for the isolated shared-inbox harness."""
import os
from pathlib import Path
from uuid import uuid4
import sqlite3
from communications_local_app import app  # also enforces isolated DB and Twilio network deny
from app.services import callrail_service

if os.environ.get('COMMUNICATIONS_ISOLATED_LOCAL') != '1':
    raise RuntimeError('CallRail simulator requires the isolated communications harness')
if any(os.environ.get(name) not in ('', 'false', None) for name in (
    'SMS_TENANT_ROUTING_ENABLED', 'SMS_AUTOMATION_OUTBOX_ENABLED', 'SMS_RECOVERY_ENABLED')):
    raise RuntimeError('All automation/routing flags must remain off for the CallRail harness')
os.environ['CALLRAIL_LOCAL_SIGNING'] = os.environ['LOCAL_WEBHOOK_SECRET']

async def simulated_send(context, body, to, *, source='manual'):
    if source != 'manual' or len(body) > 140 or to != context.customer_phone:
        raise RuntimeError('Invalid synthetic manual send')
    with sqlite3.connect(Path(__file__).resolve().parents[1] / '.communications-provider.sqlite') as ledger:
        ledger.execute('CREATE TABLE IF NOT EXISTS callrail_calls (id TEXT PRIMARY KEY, created_at TEXT DEFAULT CURRENT_TIMESTAMP)')
        ledger.execute('INSERT INTO callrail_calls (id) VALUES (?)', (str(uuid4()),))
    return {'conversation_id': 'syntheticDay1'}

callrail_service.send = simulated_send
