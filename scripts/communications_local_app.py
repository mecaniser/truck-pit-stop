"""Local-only ASGI entry point: real application/auth with a simulated SMS adapter."""
import os
from pathlib import Path
import sqlite3
import uuid

from app.core.config import settings

if settings.ENVIRONMENT != 'development':
    raise RuntimeError('Simulation is permitted only in explicit local development')

if os.environ.get('COMMUNICATIONS_ISOLATED_LOCAL') != '1' or '@127.0.0.1:55460/communications_local' not in settings.DATABASE_URL:
    raise RuntimeError('Local harness requires the isolated communications database')
if settings.TWILIO_ACCOUNT_SID or settings.TWILIO_AUTH_TOKEN != os.environ.get('LOCAL_WEBHOOK_SECRET'):
    raise RuntimeError('Real SMS credentials are prohibited in this harness')

# Last-resort guard covers accidental legacy Twilio paths as well.
from twilio.http.http_client import TwilioHttpClient

def deny_twilio_network(*args, **kwargs):
    raise RuntimeError('Real Twilio network access is disabled in the isolated inbox sandbox')

TwilioHttpClient.request = deny_twilio_network

LEDGER = Path(__file__).resolve().parents[1] / '.communications-provider.sqlite'

class SimulatedSMSSender:
    mode = 'simulated'
    ready = True

    async def send(self, *, body, from_number, to_number, status_callback):
        # Separate durable store intentionally survives application rollback and restart.
        # Contents are synthetic; body is omitted to avoid training a PII logging pattern.
        sid = 'SM' + uuid.uuid4().hex
        with sqlite3.connect(LEDGER) as ledger:
            ledger.execute('CREATE TABLE IF NOT EXISTS calls (sid TEXT PRIMARY KEY, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, outcome TEXT NOT NULL)')
            ledger.execute('CREATE TABLE IF NOT EXISTS control (id INTEGER PRIMARY KEY CHECK (id = 1), outcome TEXT NOT NULL)')
            ledger.execute('BEGIN IMMEDIATE')
            control = ledger.execute('SELECT outcome FROM control WHERE id=1').fetchone()
            outcome = control[0] if control else 'accepted'
            ledger.execute('DELETE FROM control WHERE id=1')
            ledger.execute('INSERT INTO calls (sid, outcome) VALUES (?, ?)', (sid, outcome))
        if outcome == 'unknown':
            raise TimeoutError('Synthetic timeout after provider acceptance')
        if outcome == 'rejected':
            from twilio.base.exceptions import TwilioRestException
            raise TwilioRestException(400, '/simulated/messages', msg='Synthetic rejected recipient', code=21211)
        return {'sid': sid, 'status': 'queued'}

from app.main import app
from app.services.communications_service import get_sms_sender

sender = SimulatedSMSSender()
app.dependency_overrides[get_sms_sender] = lambda: sender


if settings.SMS_TENANT_ROUTING_ENABLED:
    from types import SimpleNamespace
    from app.services import tenant_sms_routing as routing
    from app.services.communications_service import LiveSMSSender

    class FakeManagedClient:
        def __init__(self, context):
            self.context = context
            self.messages = self

        def create(self, **payload):
            if payload.get('from_') != self.context.sender_phone or payload.get('messaging_service_sid') != self.context.messaging_service_sid:
                raise RuntimeError('Synthetic provider rejected incorrect account/sender/service binding')
            sid = 'SM' + uuid.uuid4().hex
            with sqlite3.connect(LEDGER) as ledger:
                ledger.execute('CREATE TABLE IF NOT EXISTS managed_calls (sid TEXT PRIMARY KEY, account_sid TEXT NOT NULL, service_sid TEXT NOT NULL, sender TEXT NOT NULL, recipient TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)')
                ledger.execute('INSERT INTO managed_calls (sid,account_sid,service_sid,sender,recipient) VALUES (?,?,?,?,?)', (sid,self.context.account_sid,self.context.messaging_service_sid,payload['from_'],payload['to']))
            return SimpleNamespace(sid=sid,status='queued')

    routing.client_for = FakeManagedClient

    class SimulatedManagedSender(LiveSMSSender):
        mode = 'simulated'

    sender = SimulatedManagedSender()
    app.dependency_overrides[get_sms_sender] = lambda: sender
