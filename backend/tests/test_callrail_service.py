"""Manual CallRail adapter: synthetic fixtures and isolated PostgreSQL only."""
import base64
import hashlib
import hmac
import os
from datetime import datetime, timezone, timedelta
from uuid import UUID, uuid4
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
@pytest.mark.parametrize("status", [200, 201])
async def test_send_one_http_attempt_conversation_is_not_message_id(monkeypatch, context, status):
    monkeypatch.setenv('CALLRAIL_TEST', 'synthetic-key')
    calls = []
    async def handler(request):
        calls.append(request)
        return httpx.Response(status, json={'id': 'conversation1', 'company_id': context.company_id,
            'customer_phone_number': context.customer_phone, 'current_tracking_number': context.sender_phone,
            'current_tracker_id': context.tracker_id})
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(svc.httpx, 'AsyncClient', lambda **kwargs: client)
    assert await svc.send(context, 'manual test', context.customer_phone) == {'conversation_id': 'conversation1'}
    assert len(calls) == 1
    assert calls[0].url.host == 'api.callrail.com'
    assert calls[0].headers['authorization'] == 'Token token="synthetic-key"'


@pytest.mark.asyncio
@pytest.mark.parametrize('status', [202, 204, 302, 408, 429, 500])
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
@pytest.mark.parametrize('status', [200, 201])
@pytest.mark.parametrize('changed', [
    {'id': ''}, {'id': 'foreign/id'}, {'company_id': 'COMforeign'},
    {'customer_phone_number': '+15005559999'},
    {'current_tracking_number': '+15005559999'},
    {'current_tracker_id': 'TRKforeign'},
])
async def test_success_status_keeps_scope_validation_and_one_attempt(monkeypatch, context, status, changed):
    monkeypatch.setenv('CALLRAIL_TEST', 'synthetic-key')
    calls = []
    async def handler(request):
        calls.append(request)
        payload = {'id': 'conversation1', 'company_id': context.company_id,
            'customer_phone_number': context.customer_phone, 'current_tracking_number': context.sender_phone,
            'current_tracker_id': context.tracker_id}
        return httpx.Response(status, json={**payload, **changed})
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(svc.httpx, 'AsyncClient', lambda **kwargs: client)
    with pytest.raises(RuntimeError, match='requires reconciliation'):
        await svc.send(context, 'manual test', context.customer_phone)
    assert len(calls) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize('status', [200, 201])
async def test_malformed_success_body_remains_unknown_without_retry(monkeypatch, context, status):
    monkeypatch.setenv('CALLRAIL_TEST', 'synthetic-key')
    calls = []
    async def handler(request):
        calls.append(request)
        return httpx.Response(status, content=b'not json')
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(svc.httpx, 'AsyncClient', lambda **kwargs: client)
    with pytest.raises(ValueError):
        await svc.send(context, 'manual test', context.customer_phone)
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_forbidden_remains_definitive_rejection_without_retry(monkeypatch, context):
    monkeypatch.setenv('CALLRAIL_TEST', 'synthetic-key')
    calls = []
    async def handler(request):
        calls.append(request)
        return httpx.Response(403, json={})
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(svc.httpx, 'AsyncClient', lambda **kwargs: client)
    with pytest.raises(svc.CallRailRejected):
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


@pytest.mark.asyncio
@pytest.mark.parametrize('status', [200, 201])
@pytest.mark.parametrize('current_tracker, initial_tracker, accepted', [
    (None, 'TRK123', True), (None, 'TRKother', False), ('TRKother', 'TRK123', False), ('', 'TRK123', False)])
async def test_send_documented_null_tracker_fallback(monkeypatch, context, current_tracker, initial_tracker, accepted, status):
    monkeypatch.setenv('CALLRAIL_TEST', 'synthetic-key')
    async def handler(request):
        return httpx.Response(status, json={'id': 'conversation1', 'company_id': context.company_id,
            'customer_phone_number': context.customer_phone, 'current_tracking_number': context.sender_phone,
            'current_tracker_id': current_tracker, 'initial_tracker_id': initial_tracker})
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(svc.httpx, 'AsyncClient', lambda **kwargs: client)
    if accepted:
        assert await svc.send(context, 'manual test', context.customer_phone) == {'conversation_id': 'conversation1'}
    else:
        with pytest.raises(RuntimeError):
            await svc.send(context, 'manual test', context.customer_phone)


@isolated
@pytest.mark.asyncio
async def test_import_documented_tracker_fallback_preserves_sender_guard(mapped):
    db, binding, mapping, customer, thread = mapped
    record = {'id': 'conversation1', 'company_id': binding.company_id, 'current_tracker_id': None,
        'initial_tracker_id': binding.tracker_id, 'current_tracking_number': binding.sender_phone,
        'customer_phone_number': customer.phone, 'messages': []}
    assert await svc.import_conversation(db, binding.id, thread.id, record) == []
    record['current_tracker_id'] = 'TRKwrong'
    with pytest.raises(HTTPException):
        await svc.import_conversation(db, binding.id, thread.id, record)
    record['current_tracker_id'] = None
    record['current_tracking_number'] = None
    record['initial_tracking_number'] = binding.sender_phone
    with pytest.raises(HTTPException):
        await svc.import_conversation(db, binding.id, thread.id, record)


@isolated
@pytest.mark.asyncio
async def test_api_actual_sci_shape_requires_sender_proof_and_preserves_mms(mapped):
    db, binding, mapping, customer, thread = mapped
    now = datetime.now(timezone.utc).isoformat()
    record = {'id': 'allcontacthistory', 'company_id': binding.company_id, 'current_tracker_id': binding.tracker_id,
        'current_tracking_number': binding.sender_phone, 'customer_phone_number': customer.phone,
        'messages': [
            {'id': 'SCIolderOtherTracker', 'content': 'Old website conversation', 'created_at': now,
             'direction': 'incoming', 'message_type': 'sms', 'sms_thread': {'id': 'SMTday1'}},
            {'id': 'SCIverifiedIncoming', 'content': 'Synthetic reply', 'created_at': now,
             'direction': 'incoming', 'message_type': 'sms', 'sms_thread': {'id': 'SMTday2'}},
            {'id': 'SCIverifiedMms', 'content': 'Attachment caption', 'created_at': now,
             'direction': 'incoming', 'message_type': 'mms', 'media_urls': []},
        ]}
    results = await svc.import_conversation(db, binding.id, thread.id, record,
        verified_message_ids={'SCIverifiedIncoming', 'SCIverifiedMms'})
    await db.commit()
    assert [row.get('reason', row['status']) for row in results] == ['historical_sender_unproven', 'received', 'received']
    message = await db.scalar(select(SMSMessage).where(SMSMessage.thread_id == thread.id, SMSMessage.provider_message_id == 'SCIverifiedIncoming'))
    mms = await db.scalar(select(SMSMessage).where(SMSMessage.thread_id == thread.id, SMSMessage.provider_message_id == 'SCIverifiedMms'))
    assert mms.body == 'Attachment caption\n\n' + svc.ATTACHMENT_NOTICE
    assert message.provider_message_id == 'SCIverifiedIncoming'
    assert message.body == 'Synthetic reply' and message.twilio_message_sid is None
    # API SCI id and signed webhook SCI resource are one message, even when the
    # webhook adds a previously unknown numeric alias.
    callback = event(); callback.update(id=777, resource_id='SCIverifiedIncoming', content='Synthetic reply', timestamp=now)
    assert (await svc.apply_event(db, binding.id, callback, 'received'))['status'] == 'duplicate'
    await db.commit()
    results = await svc.import_conversation(db, binding.id, thread.id, record)
    assert results[1]['status'] == 'duplicate'
    assert await db.scalar(select(func.count()).select_from(SMSMessage).where(SMSMessage.thread_id == thread.id)) == 2


@isolated
@pytest.mark.asyncio
async def test_live_sci_only_receipt_deduplicates_api_import(mapped):
    db, binding, mapping, customer, thread = mapped
    payload = event(); payload.pop('id')
    payload['resource_id'] = 'SCIliveOnly'
    first = await svc.apply_event(db, binding.id, payload, 'received'); await db.commit()
    record = {'id': 'conversation1', 'company_id': binding.company_id, 'current_tracker_id': binding.tracker_id,
        'current_tracking_number': binding.sender_phone, 'customer_phone_number': customer.phone,
        'messages': [{'id': 'SCIliveOnly', 'content': payload['content'], 'created_at': payload['timestamp'],
                      'direction': 'incoming', 'message_type': 'sms'}]}
    imported = await svc.import_conversation(db, binding.id, thread.id, record)
    assert imported[0]['status'] == 'duplicate' and imported[0]['message_id'] == first['message_id']
    assert await db.scalar(select(func.count()).select_from(SMSMessage).where(SMSMessage.thread_id == thread.id)) == 1
    numeric_only = event(); numeric_only.pop('resource_id')
    assert (await svc.apply_event(db, binding.id, numeric_only, 'received'))['reason'] == 'missing_message_identity'


@isolated
@pytest.mark.asyncio
async def test_sender_options_tenant_scope_noop_restore_and_phone_conflict(mapped):
    from app.db.models.tenant import Tenant
    from app.db.models.customer import Customer
    from app.db.models.message_thread import MessageThread
    db, binding, mapping, customer, thread = mapped
    tenant = await db.get(Tenant, binding.tenant_id)
    tenant.sms_phone_number = '+1'+str(2000000000 + uuid4().int % 7000000000)
    other_tenant = Tenant(name='Other tenant', slug='cr-other-'+uuid4().hex)
    db.add(other_tenant); await db.flush()
    foreign = CallRailNumberBinding(tenant_id=other_tenant.id, account_id='ACC'+uuid4().hex, company_id='COMother',
        tracker_id='TRKother', sender_phone='+15005550999', credential_ref='CALLRAIL_TEST', signing_secret_ref='CALLRAIL_SIGNING', enabled=True)
    db.add(foreign); await db.commit()
    await svc.lock_sender_bindings(db, tenant.id)
    options = await svc.sender_context(db, tenant, thread)
    assert options['selected_sender_id'] == 'twilio'
    assert options['sender_mode'] == 'initiation' and not options['sender_selection_allowed']
    assert 'sms_sender_options' not in options
    assert await svc.set_sender(db, tenant, thread, binding.id) is False
    assert await svc.set_sender(db, tenant, thread, None) is True
    await db.flush()
    assert (await svc.sender_context(db, tenant, thread))['selected_sender_id'] == 'twilio'
    assert await svc.set_sender(db, tenant, thread, None) is False
    assert await svc.set_sender(db, tenant, thread, binding.id) is True
    assert mapping.deleted_at is None
    with pytest.raises(HTTPException) as error:
        await svc.set_sender(db, tenant, thread, foreign.id)
    assert error.value.status_code == 404
    duplicate = Customer(tenant_id=tenant.id, first_name='ETS', last_name='Preserved',
        email=uuid4().hex+'@example.test', phone=customer.phone)
    db.add(duplicate); await db.flush()
    other_thread = MessageThread(tenant_id=tenant.id, customer_id=duplicate.id, customer_phone=customer.phone)
    db.add(other_thread); await db.flush()
    with pytest.raises(HTTPException) as error:
        await svc.set_sender(db, tenant, other_thread, binding.id)
    assert error.value.detail['code'] == 'callrail_phone_conflict'
    binding.enabled = False
    await db.flush()
    options = await svc.sender_context(db, tenant, thread)
    assert options['selected_sender_id'] == 'twilio'
    assert 'sms_sender_options' not in options
    with pytest.raises(HTTPException) as error:
        await svc.set_sender(db, tenant, thread, binding.id)
    assert error.value.detail['code'] == 'callrail_binding_disabled'


@isolated
@pytest.mark.asyncio
async def test_sender_patch_stale_version_and_pending_switch_hold(mapped, monkeypatch):
    from app.db.models.tenant import Tenant
    from app.db.models.user import User
    from app.db.models.communication import SMSSendOperation
    from app.db.models.sms_message import SMSMessageDirection, SMSMessageSource, SMSDeliveryStatus
    from app.api.v1.endpoints.communications import patch_sender, SenderPatch
    from app.services import communications_service as communication
    db, binding, mapping, customer, thread = mapped
    tenant = await db.get(Tenant, binding.tenant_id)
    tenant.messaging_enabled = True
    user = User(tenant_id=tenant.id, first_name='Test', last_name='Staff', email=uuid4().hex+'@example.test',
        hashed_password='disabled', role='garage_owner', is_active=True)
    db.add(user); await db.commit()
    class Sender:
        mode = 'simulated'
        ready = True
    with pytest.raises(HTTPException) as error:
        await patch_sender(thread.id, SenderPatch(expected_version=99, binding_id=None), db, user, Sender())
    assert error.value.detail['code'] == 'sender_managed_automatically'
    await db.rollback()
    await db.refresh(thread); await db.refresh(tenant); await db.refresh(user); await db.refresh(binding); await db.refresh(customer)
    # Automatic sender endpoint refuses every mutation, including no-op requests.
    with pytest.raises(HTTPException) as error:
        await patch_sender(thread.id, SenderPatch(expected_version=1, binding_id=None), db, user, Sender())
    assert error.value.detail['code'] == 'sender_managed_automatically'
    message = SMSMessage(tenant_id=tenant.id, thread_id=thread.id, customer_id=customer.id,
        direction=SMSMessageDirection.OUTBOUND, source=SMSMessageSource.MANUAL, body='Pending',
        delivery_status=SMSDeliveryStatus.PENDING)
    db.add(message); await db.flush()
    operation = SMSSendOperation(tenant_id=tenant.id, thread_id=thread.id, message_id=message.id, actor_id=user.id,
        idempotency_key=uuid4().hex, payload_hash='a'*64, channel_account_id=uuid4(), contact_identity_id=uuid4(),
        from_number=binding.sender_phone, to_number=customer.phone, body='Pending', state='pending', attempt_count=0)
    db.add(operation); await db.commit()
    with pytest.raises(HTTPException) as error:
        await patch_sender(thread.id, SenderPatch(expected_version=2, binding_id=binding.id), db, user, Sender())
    assert error.value.detail['code'] == 'sender_managed_automatically'


@isolated
@pytest.mark.asyncio
async def test_competing_sender_selection_serializes_same_phone(mapped):
    import asyncio
    from app.db.session import AsyncSessionLocal
    from app.db.models.tenant import Tenant
    from app.db.models.customer import Customer
    from app.db.models.message_thread import MessageThread
    db, binding, mapping, customer, thread = mapped
    other = Customer(tenant_id=binding.tenant_id, first_name='Other', last_name='Source',
        email=uuid4().hex+'@example.test', phone=customer.phone)
    alternate = CallRailNumberBinding(tenant_id=binding.tenant_id, account_id=binding.account_id,
        company_id=binding.company_id, tracker_id='TRKsecond', sender_phone='+15005550003',
        credential_ref='CALLRAIL_TEST', signing_secret_ref='CALLRAIL_SIGNING', enabled=True)
    db.add_all([other, alternate]); await db.flush()
    other_thread = MessageThread(tenant_id=binding.tenant_id, customer_id=other.id, customer_phone=customer.phone)
    db.add(other_thread); await db.commit()
    tenant_id, target_id = binding.tenant_id, alternate.id
    async def select_sender(thread_id):
        async with AsyncSessionLocal() as session:
            tenant = await session.get(Tenant, tenant_id)
            await svc.lock_sender_bindings(session, tenant_id)
            locked_thread = await session.scalar(select(MessageThread).where(MessageThread.id == thread_id).with_for_update())
            try:
                await svc.set_sender(session, tenant, locked_thread, target_id)
                await session.commit()
                return 'selected'
            except HTTPException as error:
                await session.rollback()
                return error.detail['code']
    results = await asyncio.gather(select_sender(thread.id), select_sender(other_thread.id))
    assert sorted(results) == ['callrail_phone_conflict', 'selected']


@isolated
@pytest.mark.asyncio
async def test_sender_change_holds_unknown_automated_recipient(mapped):
    from app.db.models.tenant import Tenant
    from app.db.models.notification import Notification
    from app.db.models.automated_sms import AutomatedSMSOperation
    db, binding, mapping, customer, thread = mapped
    tenant = await db.get(Tenant, binding.tenant_id)
    receipt = Notification(tenant_id=tenant.id, type='sms', status='pending', body='Automated fixture', recipient_phone=customer.phone)
    db.add(receipt); await db.flush()
    operation = AutomatedSMSOperation(tenant_id=tenant.id, event_key=uuid4().hex, domain_event_id=uuid4().hex,
        template_name='test', template_version='1', recipient_kind='customer', recipient_id=customer.id,
        from_number='+15005550000', to_number=customer.phone, body='Automated fixture', payload_hash='a'*64,
        notification_id=receipt.id, state='unknown', attempt_count=1, reconciliation_state='required', delivery_status='pending')
    db.add(operation); await db.commit()
    await svc.lock_sender_bindings(db, tenant.id)
    with pytest.raises(HTTPException) as error:
        await svc.set_sender(db, tenant, thread, None)
    assert error.value.detail['code'] == 'ambiguous_outcome'
    assert mapping.deleted_at is None


@isolated
@pytest.mark.asyncio
async def test_sender_change_holds_unknown_manual_same_phone_other_thread(mapped):
    from app.db.models.tenant import Tenant
    from app.db.models.customer import Customer
    from app.db.models.message_thread import MessageThread
    from app.db.models.user import User
    from app.db.models.communication import SMSSendOperation
    from app.db.models.sms_message import SMSMessageDirection, SMSMessageSource, SMSDeliveryStatus
    db, binding, mapping, customer, thread = mapped
    tenant = await db.get(Tenant, binding.tenant_id)
    duplicate = Customer(tenant_id=tenant.id, first_name='ETS', last_name='Duplicate',
        email=uuid4().hex+'@example.test', phone=customer.phone)
    user = User(tenant_id=tenant.id, first_name='Staff', last_name='Test', email=uuid4().hex+'@example.test',
        hashed_password='disabled', role='garage_owner', is_active=True)
    alternate = CallRailNumberBinding(tenant_id=tenant.id, account_id=binding.account_id,
        company_id=binding.company_id, tracker_id='TRKalternate', sender_phone='+15005550004',
        credential_ref='CALLRAIL_TEST', signing_secret_ref='CALLRAIL_SIGNING', enabled=True)
    db.add_all([duplicate, user, alternate]); await db.flush()
    duplicate_thread = MessageThread(tenant_id=tenant.id, customer_id=duplicate.id, customer_phone=duplicate.phone)
    db.add(duplicate_thread); await db.flush()
    message = SMSMessage(tenant_id=tenant.id, thread_id=thread.id, customer_id=customer.id,
        direction=SMSMessageDirection.OUTBOUND, source=SMSMessageSource.MANUAL, body='Held fixture',
        delivery_status=SMSDeliveryStatus.PENDING)
    db.add(message); await db.flush()
    operation = SMSSendOperation(tenant_id=tenant.id, thread_id=thread.id, message_id=message.id, actor_id=user.id,
        idempotency_key=uuid4().hex, payload_hash='a'*64, channel_account_id=uuid4(), contact_identity_id=uuid4(),
        from_number=binding.sender_phone, to_number=customer.phone, body='Held fixture', state='unknown', attempt_count=1)
    db.add(operation); await db.commit()
    await svc.lock_sender_bindings(db, tenant.id)
    with pytest.raises(HTTPException) as error:
        await svc.set_sender(db, tenant, duplicate_thread, alternate.id)
    assert error.value.detail['code'] == 'ambiguous_outcome'
    assert await db.scalar(select(CallRailConversation.id).where(CallRailConversation.thread_id == duplicate_thread.id)) is None
    assert mapping.binding_id == binding.id and mapping.deleted_at is None


@isolated
@pytest.mark.asyncio
async def test_inbound_routes_survive_outbound_sender_changes_and_twilio(mapped):
    from app.db.models.tenant import Tenant
    from app.db.models.customer import Customer
    from app.db.models.message_thread import MessageThread
    db, binding, mapping, customer, thread = mapped
    tenant = await db.get(Tenant, binding.tenant_id)
    alternate = CallRailNumberBinding(tenant_id=tenant.id, account_id=binding.account_id,
        company_id=binding.company_id, tracker_id='TRKpreserved', sender_phone='+15005550005',
        credential_ref='CALLRAIL_TEST', signing_secret_ref='CALLRAIL_SIGNING', enabled=True)
    duplicate = Customer(tenant_id=tenant.id, first_name='ETS', last_name='Source',
        email=uuid4().hex+'@example.test', phone=customer.phone)
    db.add_all([alternate, duplicate]); await db.flush()
    duplicate_thread = MessageThread(tenant_id=tenant.id, customer_id=duplicate.id, customer_phone=customer.phone)
    db.add(duplicate_thread); await db.commit()
    await svc.lock_sender_bindings(db, tenant.id)
    assert await svc.set_sender(db, tenant, thread, alternate.id)
    await db.commit()
    assert mapping.binding_id == binding.id and mapping.deleted_at is None and not mapping.selected_for_sending
    assert (await svc.resolve_for_thread(db, tenant.id, thread.id)).binding_id == alternate.id
    receipt_a = event(); receipt_a.update(id=98701, resource_id='SCIafterB', content='Reply to original A')
    result = await svc.apply_event(db, binding.id, receipt_a, 'received'); await db.commit()
    assert result['status'] == 'received'
    assert (await db.get(SMSMessage, UUID(result['message_id']))).thread_id == thread.id
    await svc.lock_sender_bindings(db, tenant.id)
    assert await svc.set_sender(db, tenant, thread, None)
    await db.commit()
    assert await svc.resolve_for_thread(db, tenant.id, thread.id) is None
    assert (await svc.sender_context(db, tenant, thread))['selected_sender_id'] == str(binding.id)
    receipt_a.update(id=98702, resource_id='SCIafterTwilioA', content='A after Twilio')
    assert (await svc.apply_event(db, binding.id, receipt_a, 'received'))['status'] == 'received'
    receipt_b = dict(receipt_a, id=98703, resource_id='SCIafterTwilioB', destination_number=alternate.sender_phone,
                     content='B after Twilio')
    assert (await svc.apply_event(db, alternate.id, receipt_b, 'received'))['status'] == 'received'
    await db.commit()
    # Previous sender reservations still belong to the canonical DBN thread.
    await svc.lock_sender_bindings(db, tenant.id)
    with pytest.raises(HTTPException) as error:
        await svc.set_sender(db, tenant, duplicate_thread, binding.id)
    assert error.value.detail['code'] == 'callrail_phone_conflict'
    assert await svc.set_sender(db, tenant, thread, binding.id)
    await db.commit()
    routes = (await db.scalars(select(CallRailConversation).where(CallRailConversation.thread_id == thread.id))).all()
    assert len(routes) == 2 and sum(row.selected_for_sending for row in routes) == 1
    assert next(row for row in routes if row.selected_for_sending).binding_id == binding.id
    # Concurrent outbound choices serialize and retain exactly one selection.
    import asyncio
    from app.db.session import AsyncSessionLocal
    tenant_id, thread_id = tenant.id, thread.id
    async def choose(binding_id):
        async with AsyncSessionLocal() as session:
            current_tenant = await session.get(Tenant, tenant_id)
            await svc.lock_sender_bindings(session, tenant_id)
            locked = await session.scalar(select(MessageThread).where(MessageThread.id == thread_id).with_for_update())
            await svc.set_sender(session, current_tenant, locked, binding_id)
            await session.commit()
    binding_a_id, binding_b_id = binding.id, alternate.id
    await db.rollback()
    await asyncio.gather(choose(binding_a_id), choose(binding_b_id))
    selected_count = await db.scalar(select(func.count()).select_from(CallRailConversation).where(
        CallRailConversation.thread_id == thread_id, CallRailConversation.selected_for_sending.is_(True),
        CallRailConversation.deleted_at.is_(None)))
    assert selected_count == 1


@pytest.fixture(autouse=True)
def synthetic_shared_budget(monkeypatch):
    from app.services import callrail_budget
    async def reserve(*args):
        return callrail_budget.Permit(str(uuid4()), datetime.now(timezone.utc) + timedelta(days=1))
    async def complete(*args):
        pass
    monkeypatch.setattr(callrail_budget, 'reserve', reserve)
    monkeypatch.setattr(callrail_budget, 'complete', complete)
