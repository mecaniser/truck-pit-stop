"""Manual CallRail adapter: synthetic fixtures and isolated PostgreSQL only."""
import base64
import hashlib
import hmac
import os
from datetime import datetime, timezone, timedelta
from uuid import uuid4
import httpx
import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy import select, func
from app.services import callrail_service as svc
from app.db.models.callrail import CallRailNumberBinding, CallRailConversation, CallRailMessageAlias, CallRailQuarantine
from app.db.models.sms_message import SMSMessage


def test_raw_body_signature_and_env_credentials(monkeypatch):
    raw = b'{"content":"a b"}'
    signature = base64.b64encode(hmac.new(b'signing', raw, hashlib.sha1).digest()).decode()
    assert svc.valid_signature(raw, signature, 'signing')
    assert not svc.valid_signature(raw.replace(b'a b', b'ab'), signature, 'signing')
    assert not svc.valid_signature(raw, None, 'signing')
    monkeypatch.setenv('SECRET_KEY', 'must not resolve')
    with pytest.raises(HTTPException):
        svc.secret('SECRET_KEY')
    monkeypatch.setenv('CALLRAIL_TEST', 'synthetic-key')
    assert svc.secret('CALLRAIL_TEST') == 'synthetic-key'


@pytest.fixture
def context():
    return svc.CallRailContext(uuid4(), uuid4(), uuid4(), uuid4(), 'ACC123', 'COM123', 'TRK123', '+15005550001', '+15005550002', 'CALLRAIL_TEST')


@pytest.mark.asyncio
async def test_send_one_http_attempt_conversation_is_not_message_id(monkeypatch, context):
    monkeypatch.setenv('CALLRAIL_TEST', 'synthetic-key')
    calls = []
    async def handler(request):
        calls.append(request)
        return httpx.Response(201, json={'id': 'conversation1', 'company_id': context.company_id,
            'customer_phone_number': context.customer_phone, 'current_tracking_number': context.sender_phone,
            'current_tracker_id': context.tracker_id})
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(svc.httpx, 'AsyncClient', lambda **kwargs: client)
    assert await svc.send(context, 'manual test', context.customer_phone) == {'conversation_id': 'conversation1'}
    assert len(calls) == 1
    assert calls[0].url.host == 'api.callrail.com'
    assert calls[0].headers['authorization'] == 'Token token="synthetic-key"'


@pytest.mark.asyncio
@pytest.mark.parametrize('status', [302, 408, 429, 500])
async def test_uncertain_response_never_retries(monkeypatch, context, status):
    monkeypatch.setenv('CALLRAIL_TEST', 'synthetic-key')
    calls = []
    async def handler(request):
        calls.append(request)
        return httpx.Response(status, json={})
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(svc.httpx, 'AsyncClient', lambda **kwargs: client)
    with pytest.raises(RuntimeError):
        await svc.send(context, 'manual test', context.customer_phone)
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_automated_and_changed_contact_never_reach_provider(context):
    for kwargs in ({'source': 'automated'}, {}):
        with pytest.raises(HTTPException):
            await svc.send(context, 'hello', '+15005559999', **kwargs)
    with pytest.raises(HTTPException):
        await svc.send(context, 'a'*141, context.customer_phone)
    with pytest.raises(HTTPException):
        await svc.send(context, 'hello', context.customer_phone, source='automated')


isolated = pytest.mark.skipif(os.getenv('COMMUNICATIONS_ISOLATED_LOCAL') != '1', reason='dedicated isolated PostgreSQL required')


@pytest_asyncio.fixture
async def mapped():
    from app.db.session import AsyncSessionLocal, engine
    from app.db.models.tenant import Tenant
    from app.db.models.customer import Customer
    from app.db.models.message_thread import MessageThread
    async with AsyncSessionLocal() as db:
        tenant = Tenant(name='CallRail synthetic', slug='cr-' + uuid4().hex, is_active=True)
        db.add(tenant); await db.flush()
        customer = Customer(tenant_id=tenant.id, first_name='Synthetic', last_name='Contact', email=uuid4().hex+'@example.test', phone='+15005550002')
        db.add(customer); await db.flush()
        thread = MessageThread(tenant_id=tenant.id, customer_id=customer.id, customer_phone=customer.phone)
        binding = CallRailNumberBinding(tenant_id=tenant.id, account_id='ACC'+uuid4().hex, company_id='COM123',
            tracker_id='TRK123', sender_phone='+15005550001', credential_ref='CALLRAIL_TEST', signing_secret_ref='CALLRAIL_SIGNING', enabled=True)
        db.add_all([thread, binding]); await db.flush()
        mapping = CallRailConversation(tenant_id=tenant.id, thread_id=thread.id, customer_id=customer.id,
            binding_id=binding.id, customer_phone=customer.phone)
        db.add(mapping); await db.commit()
        yield db, binding, mapping, customer, thread
        await db.rollback()
    await engine.dispose()


def event(**kwargs):
    return dict(id=12345, resource_id='SCIabc123', source_number='+15005550002', destination_number='+15005550001',
        content='Test reply', company_resource_id='COM123', conversation_id='conversation1', message_type='sms',
        timestamp=datetime.now(timezone.utc).isoformat(), **kwargs)


@isolated
@pytest.mark.asyncio
async def test_signed_alias_and_api_import_deduplicate(mapped):
    db, binding, mapping, customer, thread = mapped
    payload = event()
    first = await svc.apply_event(db, binding.id, payload, 'received'); await db.commit()
    again = await svc.apply_event(db, binding.id, payload, 'received'); await db.commit()
    assert again['status'] == 'duplicate' and again['message_id'] == first['message_id']
    imported = {'id': 'conversation1', 'company_id': binding.company_id, 'current_tracker_id': binding.tracker_id,
        'current_tracking_number': binding.sender_phone, 'customer_phone_number': customer.phone,
        'messages': [{'id': 12345, 'content': payload['content'], 'created_at': payload['timestamp'], 'direction': 'incoming', 'type': 'sms'}]}
    results = await svc.import_conversation(db, binding.id, thread.id, imported); await db.commit()
    assert results[0]['status'] == 'duplicate'
    assert await db.scalar(select(func.count()).select_from(SMSMessage).where(SMSMessage.thread_id == thread.id)) == 1
    assert await db.scalar(select(func.count()).select_from(CallRailMessageAlias).where(CallRailMessageAlias.account_id == binding.account_id)) == 2
    message = await db.scalar(select(SMSMessage).where(SMSMessage.thread_id == thread.id))
    assert message.twilio_message_sid is None and message.provider == 'callrail'
    assert thread.unread_count_staff == 1


@isolated
@pytest.mark.asyncio
async def test_tenant_phone_rebound_disabled_and_quarantine(mapped):
    db, binding, mapping, customer, thread = mapped
    assert await svc.resolve_for_thread(db, uuid4(), thread.id) is None
    customer.phone = '+15005559999'; await db.commit()
    with pytest.raises(HTTPException):
        await svc.resolve_for_thread(db, binding.tenant_id, thread.id)
    payload = event()
    result = await svc.apply_event(db, binding.id, payload, 'received'); await db.commit()
    assert result['reason'] == 'contact_changed'
    await svc.apply_event(db, binding.id, payload, 'received'); await db.commit()
    assert await db.scalar(select(func.count()).select_from(CallRailQuarantine).where(CallRailQuarantine.binding_id == binding.id)) == 1
    customer.phone = mapping.customer_phone; binding.enabled = False; await db.commit()
    with pytest.raises(HTTPException):
        await svc.resolve_for_thread(db, binding.tenant_id, thread.id)
    assert (await svc.apply_event(db, binding.id, payload, 'received'))['reason'] == 'binding_disabled'


@isolated
@pytest.mark.asyncio
async def test_unknown_wrong_company_sender_old_event_and_stop(mapped):
    db, binding, mapping, customer, thread = mapped
    cases = [('company_resource_id', 'COMother', 'company_mismatch'), ('source_number', '+15005559999', 'unmapped_contact'),
        ('destination_number', '+15005559999', 'sender_mismatch'),
        ('timestamp', (datetime.now(timezone.utc)-timedelta(days=8)).isoformat(), 'stale_timestamp')]
    for key, value, reason in cases:
        payload = event(); payload[key] = value
        assert (await svc.apply_event(db, binding.id, payload, 'received'))['reason'] == reason
    payload = event(); payload['content'] = 'STOP'
    await svc.apply_event(db, binding.id, payload, 'received'); await db.commit()
    assert customer.sms_opt_out is True
    with pytest.raises(HTTPException):
        await svc.resolve_for_thread(db, binding.tenant_id, thread.id)
    assert await svc.resolve_for_thread(db, binding.tenant_id, thread.id, allow_opt_out=True)


@isolated
@pytest.mark.asyncio
async def test_daily_conversations_and_failed_import_do_not_duplicate_or_regress(mapped):
    db, binding, mapping, customer, thread = mapped
    first = event()
    await svc.apply_event(db, binding.id, first, 'received'); await db.commit()
    next_day = event(); next_day.update(id=12346, resource_id='SCInext', conversation_id='nextday')
    assert (await svc.apply_event(db, binding.id, next_day, 'received'))['status'] == 'received'
    await db.commit()
    sent = event(); sent.update(id=12347, resource_id='SCIout', source_number=binding.sender_phone,
        destination_number=customer.phone, content='Outbound')
    result = await svc.apply_event(db, binding.id, sent, 'sent'); await db.commit()
    await svc.apply_event(db, binding.id, sent, 'sent', historical=True, failed=True); await db.commit()
    await svc.apply_event(db, binding.id, sent, 'sent'); await db.commit()
    from uuid import UUID
    message = await db.get(SMSMessage, UUID(result['message_id']))
    assert message.delivery_status.value == 'failed'
    assert await db.scalar(select(func.count()).select_from(SMSMessage).where(SMSMessage.thread_id == thread.id)) == 3


@pytest.mark.asyncio
async def test_webhook_rejects_signature_before_payload_trust(monkeypatch):
    from fastapi import FastAPI
    from types import SimpleNamespace
    from app.api.v1.endpoints.callrail import router
    from app.core.dependencies import get_db
    app = FastAPI(); app.include_router(router)
    binding_id = uuid4()
    class DB:
        async def get(self, model, key):
            return SimpleNamespace(signing_secret_ref='CALLRAIL_SIGNING')
    async def db_dependency():
        yield DB()
    app.dependency_overrides[get_db] = db_dependency
    monkeypatch.setenv('CALLRAIL_SIGNING', 'synthetic-signing-key')
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
        response = await client.post(f'/{binding_id}/received', content=b'invalid JSON', headers={'Signature': 'bad'})
        assert response.status_code == 403
        response = await client.post(f'/{binding_id}/received', content=b'x'*65537)
        assert response.status_code == 413
        raw = b'invalid JSON'
        sig = base64.b64encode(hmac.new(b'synthetic-signing-key', raw, hashlib.sha1).digest()).decode()
        response = await client.post(f'/{binding_id}/received', content=raw, headers={'Signature': sig})
        assert response.status_code == 422


@isolated
@pytest.mark.asyncio
async def test_signed_malformed_fields_are_quarantined_not_500(mapped):
    db, binding, mapping, customer, thread = mapped
    for key, value in [('source_number', 123), ('destination_number', {}), ('message_type', []), ('timestamp', None), ('content', [])]:
        payload = event(); payload[key] = value
        assert (await svc.apply_event(db, binding.id, payload, 'received'))['status'] == 'quarantined'
    assert not svc.valid_signature(b'{}', '\u00e9', 'test')


@isolated
@pytest.mark.asyncio
async def test_sent_suffix_reconciles_once_and_ambiguous_or_late_holds(mapped):
    from app.db.models.user import User
    from app.db.models.communication import SMSSendOperation
    from app.db.models.sms_message import SMSMessageDirection, SMSMessageSource, SMSDeliveryStatus
    db, binding, mapping, customer, thread = mapped
    actor = User(tenant_id=binding.tenant_id, first_name='Test', last_name='Operator', email=uuid4().hex+'@example.test',
        hashed_password='disabled', role='garage_owner', is_active=True)
    db.add(actor); await db.flush()
    async def make_operation(body, started):
        message = SMSMessage(tenant_id=binding.tenant_id, thread_id=thread.id, customer_id=customer.id,
            direction=SMSMessageDirection.OUTBOUND, source=SMSMessageSource.MANUAL, body=body,
            from_number=binding.sender_phone, to_number=customer.phone, delivery_status=SMSDeliveryStatus.PENDING,
            provider='callrail', callrail_binding_id=binding.id, provider_account_id=binding.account_id)
        db.add(message); await db.flush()
        operation = SMSSendOperation(tenant_id=binding.tenant_id, thread_id=thread.id, message_id=message.id,
            actor_id=actor.id, idempotency_key=uuid4().hex, payload_hash='a'*64, channel_account_id=uuid4(),
            contact_identity_id=uuid4(), from_number=binding.sender_phone, to_number=customer.phone, body=body,
            state='unknown', attempt_count=1, dispatch_started_at=started, provider='callrail', callrail_binding_id=binding.id,
            provider_account_id=binding.account_id)
        db.add(operation); await db.flush()
        return operation, message
    now = datetime.now(timezone.utc)
    operation, message = await make_operation('Manual hello', now)
    await db.commit()
    sent = event(); sent.update(source_number=binding.sender_phone, destination_number=customer.phone,
        content='Manual hello\n\nReply STOP to opt out.')
    result = await svc.apply_event(db, binding.id, sent, 'sent'); await db.commit()
    assert result['message_id'] == str(message.id) and operation.state == 'accepted'
    assert operation.body == 'Manual hello' and message.body == sent['content']
    assert (await svc.apply_event(db, binding.id, sent, 'sent'))['status'] == 'duplicate'
    late, _ = await make_operation('Late hello', now-timedelta(minutes=20))
    late_payload = dict(sent, id=54321, resource_id='SCIlate', content='Late hello')
    assert (await svc.apply_event(db, binding.id, late_payload, 'sent'))['reason'] == 'unmatched_send_receipt'
    first, _ = await make_operation('Ambiguous hello', now)
    second, _ = await make_operation('Ambiguous hello', now)
    ambiguous = dict(sent, id=54322, resource_id='SCIambiguous', content='Ambiguous hello')
    assert (await svc.apply_event(db, binding.id, ambiguous, 'sent'))['reason'] == 'ambiguous_send_receipt'
