"""Public inquiry intake against isolated synthetic PostgreSQL, never real SMS."""
import asyncio
import base64
import hashlib
import hmac
import json
import os
from datetime import datetime, timezone
from uuid import uuid4, UUID
import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI, HTTPException
from sqlalchemy import select, func
from app.db.models.callrail import CallRailNumberBinding, CallRailConversation, CallRailQuarantine
from app.db.models.message_thread import MessageThread
from app.db.models.customer import Customer
from app.db.models.sms_message import SMSMessage
from app.db.models.tenant import Tenant
from app.services import callrail_service as cr, communications_service as comm

pytestmark = pytest.mark.skipif(os.getenv('COMMUNICATIONS_ISOLATED_LOCAL') != '1', reason='requires dedicated isolated PostgreSQL')


@pytest_asyncio.fixture
async def setup(monkeypatch):
    from app.db.session import AsyncSessionLocal, engine
    from app.db.models.user import User
    async with AsyncSessionLocal() as db:
        tenant = Tenant(name='Inquiry synthetic', slug='inq-'+uuid4().hex, messaging_enabled=True, sms_enabled=False)
        db.add(tenant); await db.flush()
        actor = User(tenant_id=tenant.id, first_name='Test', last_name='Staff', email=uuid4().hex+'@example.test',
            hashed_password='disabled', role='garage_owner', is_active=True)
        binding = CallRailNumberBinding(tenant_id=tenant.id, account_id='ACC'+uuid4().hex, company_id='COMsynthetic',
            tracker_id='TRKsharedPool', sender_phone='+15005550011', credential_ref='CALLRAIL_INQUIRY_API',
            signing_secret_ref='CALLRAIL_INQUIRY_SIGNING', enabled=True, accept_new_inquiries=True)
        db.add_all([actor, binding]); await db.commit()
        monkeypatch.setenv('CALLRAIL_INQUIRY_SIGNING', 'synthetic-inquiry-signing')
        async def permitted(*args, **kwargs):
            return True
        monkeypatch.setattr(comm, 'enforce_tenant_send_rate_limit', permitted)
        yield db, tenant, actor, binding
        await db.rollback()
    await engine.dispose()


def payload(binding, **values):
    result = dict(resource_id='SCI'+uuid4().hex, company_resource_id=binding.company_id,
        source_number='+15005550022', destination_number=binding.sender_phone, content='Need help with a truck',
        message_type='sms', media_urls=[], timestamp=datetime.now(timezone.utc).isoformat(), conversation_id='contact1')
    result.update(values)
    return result


async def receive(db, binding, **values):
    result = await cr.apply_event(db, binding.id, payload(binding, **values), 'received')
    await db.commit()
    return result


@pytest.mark.asyncio
async def test_new_inquiry_has_no_customer_and_can_manually_reply_once(setup, monkeypatch):
    from app.api.v1.endpoints.communications import SendRequest
    from app.db.models.communication import SMSSendOperation
    db, tenant, actor, binding = setup
    result = await receive(db, binding)
    inbound = await db.get(SMSMessage, UUID(result['message_id']))
    thread = await comm.thread_for(db, tenant.id, inbound.thread_id)
    assert thread.thread_kind == 'inquiry' and thread.customer_id is None and inbound.customer_id is None
    assert await db.scalar(select(func.count()).select_from(Customer).where(Customer.tenant_id == tenant.id)) == 0
    class Sender:
        ready = False
        mode = 'simulated'
    conversation = await comm.conversation_json(db, tenant, actor, thread, Sender())
    assert conversation['conversation_kind'] == 'inquiry' and conversation['customer_name'] == 'New inquiry'
    assert conversation['customer_id'] is None and conversation['company'] is None
    assert conversation['send_policy']['can_send'] is True and conversation['send_policy']['max_length'] == 140
    assert conversation['context']['sender_selection_allowed'] is False
    assert conversation['context']['sender_number'] == binding.sender_phone
    request = SendRequest(channel_account_id=conversation['channel_account_id'], contact_identity_id=conversation['contact_identity_id'],
        body='Manual shop reply', expected_version=conversation['version'])
    key = uuid4().hex
    operation, replay = await comm.create_operation(db, actor, tenant, thread.id, request, key, Sender())
    again, replayed = await comm.create_operation(db, actor, tenant, thread.id, request, key, Sender())
    assert operation.id == again.id and not replay and replayed
    calls = []
    async def send(context, body, to, **kwargs):
        calls.append((context.binding_id, body, to))
        return {'conversation_id': 'contact1'}
    monkeypatch.setattr(cr, 'send', send)
    operation_id, binding_id, remote_phone, tenant_id = operation.id, binding.id, thread.customer_phone, tenant.id
    await comm.dispatch_operation(db, operation_id, Sender())
    await comm.dispatch_operation(db, operation_id, Sender())
    assert calls == [(binding_id, 'Manual shop reply', remote_phone)]
    assert (await db.get(SMSSendOperation, operation_id)).state == 'accepted'
    assert await db.scalar(select(func.count()).select_from(Customer).where(Customer.tenant_id == tenant_id)) == 0


@pytest.mark.asyncio
async def test_replay_distinct_messages_and_existing_customer_are_never_guessed(setup):
    db, tenant, actor, binding = setup
    customer = Customer(tenant_id=tenant.id, first_name='Existing', last_name='DBN', email=uuid4().hex+'@example.test', phone='+15005550022')
    duplicate = Customer(tenant_id=tenant.id, first_name='Existing', last_name='ETS', email=uuid4().hex+'@example.test', phone=customer.phone)
    db.add_all([customer, duplicate]); await db.commit()
    data = payload(binding)
    first = await cr.apply_event(db, binding.id, data, 'received'); await db.commit()
    second = await cr.apply_event(db, binding.id, data, 'received'); await db.commit()
    assert second['status'] == 'duplicate' and first['message_id'] == second['message_id']
    await receive(db, binding, content='Another distinct message')
    threads = (await db.scalars(select(MessageThread).where(MessageThread.tenant_id == tenant.id))).all()
    assert len(threads) == 1 and threads[0].unread_count_staff == 2 and threads[0].customer_id is None
    assert await db.scalar(select(func.count()).select_from(Customer).where(Customer.tenant_id == tenant.id)) == 2


@pytest.mark.asyncio
async def test_two_numbers_shared_tracker_keep_separate_inquiries_and_stop(setup):
    db, tenant, actor, binding = setup
    second = CallRailNumberBinding(tenant_id=tenant.id, account_id=binding.account_id, company_id=binding.company_id,
        tracker_id=binding.tracker_id, sender_phone='+15005550012', credential_ref=binding.credential_ref,
        signing_secret_ref=binding.signing_secret_ref, enabled=True, accept_new_inquiries=True)
    db.add(second); await db.commit()
    a = await receive(db, binding)
    b = await receive(db, second)
    a_message, b_message = await db.get(SMSMessage, UUID(a['message_id'])), await db.get(SMSMessage, UUID(b['message_id']))
    assert a_message.thread_id != b_message.thread_id
    thread = await db.get(MessageThread, a_message.thread_id)
    with pytest.raises(HTTPException) as error:
        await cr.set_sender(db, tenant, thread, second.id)
    assert error.value.detail['code'] == 'inquiry_sender_locked'
    await receive(db, binding, content='STOP')
    assert thread.inquiry_opted_out is True
    with pytest.raises(HTTPException):
        await cr.resolve_for_thread(db, tenant.id, thread.id)
    binding.accept_new_inquiries = False; await db.commit()
    assert (await receive(db, binding, content='Existing inquiry still receives'))['status'] == 'received'
    assert (await receive(db, binding, source_number='+15005550099'))['reason'] == 'unmapped_contact'


@pytest.mark.asyncio
async def test_invalid_intake_sent_mms_and_disabled_never_create_inquiry(setup):
    db, tenant, actor, binding = setup
    cases = [({'message_type':'mms'}, 'received', 'unsupported_message'),
        ({'source_number':'invalid'}, 'received', 'invalid_contact_phone'),
        ({'company_resource_id':'COMforeign'}, 'received', 'company_mismatch'),
        ({'source_number':binding.sender_phone,'destination_number':'+15005550022'}, 'sent', 'unmapped_contact')]
    for values, kind, reason in cases:
        assert (await cr.apply_event(db, binding.id, payload(binding, **values), kind))['reason'] == reason
    binding.accept_new_inquiries = False; await db.flush()
    assert (await cr.apply_event(db, binding.id, payload(binding), 'received'))['reason'] == 'unmapped_contact'
    await db.commit()
    assert await db.scalar(select(func.count()).select_from(MessageThread).where(MessageThread.tenant_id == tenant.id)) == 0


@pytest.mark.asyncio
async def test_company_receiver_resolves_only_inventory_signature_and_shared_tracker(setup):
    from app.api.v1.endpoints.callrail import router
    from app.core.dependencies import get_db
    db, tenant, actor, anchor = setup
    second = CallRailNumberBinding(tenant_id=tenant.id, account_id=anchor.account_id, company_id=anchor.company_id,
        tracker_id=anchor.tracker_id, sender_phone='+15005550013', credential_ref=anchor.credential_ref,
        signing_secret_ref=anchor.signing_secret_ref, enabled=True, accept_new_inquiries=True)
    other_tenant = Tenant(name='Foreign shop', slug='foreign-inq-'+uuid4().hex, messaging_enabled=True)
    db.add(other_tenant); await db.flush()
    foreign = CallRailNumberBinding(tenant_id=other_tenant.id, account_id=anchor.account_id, company_id=anchor.company_id,
        tracker_id=anchor.tracker_id, sender_phone='+15005550014', credential_ref=anchor.credential_ref,
        signing_secret_ref=anchor.signing_secret_ref, enabled=True, accept_new_inquiries=True)
    db.add_all([second, foreign]); await db.commit()
    app = FastAPI(); app.include_router(router)
    async def dependency():
        yield db
    app.dependency_overrides[get_db] = dependency
    url = f'/{anchor.id}/company/received'
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
        async def post(data, signature=True):
            raw = json.dumps(data).encode()
            sig = base64.b64encode(hmac.new(b'synthetic-inquiry-signing', raw, hashlib.sha1).digest()).decode()
            return await client.post(url, content=raw, headers={'Signature':sig if signature else 'bad'})
        assert (await post(payload(second), signature=False)).status_code == 403
        response = await post(payload(second)); assert response.json()['status'] == 'received'
        message = await db.get(SMSMessage, UUID(response.json()['message_id']))
        assert message.callrail_binding_id == second.id
        assert (await post(payload(anchor, destination_number='+15005550999'))).json()['reason'] == 'unrecognized_company_number'
        assert (await post(payload(anchor, company_resource_id='COMforeign'))).json()['reason'] == 'company_mismatch'
        assert (await post(payload(foreign))).json()['reason'] == 'unrecognized_company_number'
        assert await db.scalar(select(func.count()).select_from(MessageThread).where(MessageThread.tenant_id == other_tenant.id)) == 0
        second.signing_secret_ref = 'CALLRAIL_OTHER_SIGNING'; await db.commit()
        assert (await post(payload(second))).json()['reason'] == 'signing_reference_mismatch'
        assert await db.scalar(select(func.count()).select_from(CallRailQuarantine).where(CallRailQuarantine.binding_id == second.id)) == 0
        assert await db.scalar(select(func.count()).select_from(CallRailQuarantine).where(CallRailQuarantine.binding_id == anchor.id)) == 4


@pytest.mark.asyncio
async def test_simultaneous_first_events_one_thread_replay_safe(setup):
    from app.db.session import AsyncSessionLocal
    db, tenant, actor, binding = setup
    binding_id, tenant_id = binding.id, tenant.id
    one, two = payload(binding), payload(binding, content='Second inbound')
    async def incoming(data):
        async with AsyncSessionLocal() as session:
            result = await cr.apply_event(session, binding_id, data, 'received')
            await session.commit()
            return result
    results = await asyncio.gather(incoming(one), incoming(one), incoming(two))
    assert sum(row['status'] == 'duplicate' for row in results) == 1
    assert await db.scalar(select(func.count()).select_from(MessageThread).where(MessageThread.tenant_id == tenant_id)) == 1
    assert await db.scalar(select(func.count()).select_from(SMSMessage).where(SMSMessage.tenant_id == tenant_id)) == 2


@pytest.mark.asyncio
async def test_inquiry_filter_search_legacy_endpoints_and_foreign_thread_are_safe(setup):
    from app.api.v1.endpoints import communications, messages
    db, tenant, actor, binding = setup
    received = await receive(db, binding, content='Specific inquiry keyword')
    sms = await db.get(SMSMessage, UUID(received['message_id']))
    class Sender:
        ready = False
        mode = 'simulated'
    page = await communications.list_conversations(limit=100, cursor=None, channel=None, conversation_kind='inquiry',
        status=None, search='Specific inquiry', db=db, user=actor, sender=Sender())
    assert len(page['items']) == 1 and page['items'][0]['id'] == sms.thread_id
    page = await communications.list_conversations(limit=100, cursor=None, channel=None, conversation_kind='customer',
        status=None, search='', db=db, user=actor, sender=Sender())
    assert page['items'] == []
    legacy = await messages.list_message_threads(limit=20, cursor=None, include_archived=False, db=db, current_user=actor)
    assert legacy.items == []
    assert (await messages.get_unread_sms_summary(db, actor)).unread_count_staff == 0
    with pytest.raises(HTTPException) as error:
        await messages.list_thread_messages(sms.thread_id, limit=50, cursor=None, db=db, current_user=actor)
    assert error.value.status_code == 404
    with pytest.raises(HTTPException) as error:
        await comm.thread_for(db, uuid4(), sms.thread_id)
    assert error.value.status_code == 404


@pytest.mark.asyncio
async def test_explicit_customer_route_wins_and_disabled_routes_do_not_spawn_inquiries(setup):
    db, tenant, actor, binding = setup
    customer = Customer(tenant_id=tenant.id, first_name='Canonical', last_name='DBN', email=uuid4().hex+'@example.test', phone='+15005550022')
    db.add(customer); await db.flush()
    thread = MessageThread(tenant_id=tenant.id, customer_id=customer.id, customer_phone=customer.phone)
    db.add(thread); await db.flush()
    route = CallRailConversation(tenant_id=tenant.id, thread_id=thread.id, binding_id=binding.id, customer_id=customer.id, customer_phone=customer.phone)
    db.add(route); await db.commit()
    result = await receive(db, binding)
    assert (await db.get(SMSMessage, UUID(result['message_id']))).thread_id == thread.id
    assert await db.scalar(select(func.count()).select_from(MessageThread).where(MessageThread.tenant_id == tenant.id, MessageThread.thread_kind == 'inquiry')) == 0
    customer.phone = '+15005550098'; await db.commit()
    assert (await receive(db, binding))['reason'] == 'contact_changed'
    assert await db.scalar(select(func.count()).select_from(MessageThread).where(MessageThread.tenant_id == tenant.id)) == 1


@pytest.mark.asyncio
async def test_inquiry_held_outcome_never_retries_and_sql_null_cannot_bypass_identity(setup, monkeypatch):
    from app.api.v1.endpoints.communications import SendRequest
    from sqlalchemy.exc import IntegrityError
    from sqlalchemy import text
    from app.db.models.communication import SMSSendOperation
    db, tenant, actor, binding = setup
    result = await receive(db, binding)
    message = await db.get(SMSMessage, UUID(result['message_id']))
    thread = await db.get(MessageThread, message.thread_id)
    class Sender:
        ready = False
        mode = 'simulated'
    view = await comm.conversation_json(db, tenant, actor, thread, Sender())
    request = SendRequest(channel_account_id=view['channel_account_id'], contact_identity_id=view['contact_identity_id'],
        body='Manual uncertain', expected_version=view['version'])
    operation, _ = await comm.create_operation(db, actor, tenant, thread.id, request, uuid4().hex, Sender())
    calls = []
    async def uncertain(*args, **kwargs):
        calls.append(True)
        raise TimeoutError()
    monkeypatch.setattr(cr, 'send', uncertain)
    operation_id, thread_id, tenant_id = operation.id, thread.id, tenant.id
    await comm.dispatch_operation(db, operation_id, Sender())
    await comm.dispatch_operation(db, operation_id, Sender())
    assert len(calls) == 1
    assert (await db.get(SMSSendOperation, operation_id)).state == 'unknown'
    current_thread = await db.get(MessageThread, thread_id)
    current_tenant = await db.get(Tenant, tenant_id)
    assert (await comm.send_policy(db, current_tenant, current_thread, Sender()))[0]['reason'] == 'ambiguous_outcome'
    # A SQL NULL provider must not satisfy the nullable-customer check by UNKNOWN.
    with pytest.raises(IntegrityError):
        async with db.begin_nested():
            await db.execute(text("INSERT INTO sms_messages(id,tenant_id,thread_id,customer_id,direction,source,body,delivery_status,provider,callrail_binding_id) VALUES(:id,:tenant,:thread,NULL,'inbound','inbound','Invalid nullable row','delivered',NULL,NULL)"),
                {'id':uuid4(),'tenant':tenant_id,'thread':thread_id})
    with pytest.raises(IntegrityError):
        async with db.begin_nested():
            await db.execute(text("INSERT INTO message_threads(id,tenant_id,thread_kind,customer_id,customer_phone,unread_count_staff) VALUES(:id,:tenant,'unknown',NULL,'+15005550099',0)"),
                {'id':uuid4(),'tenant':tenant_id})


@pytest.mark.asyncio
async def test_inquiry_policy_retains_stop_and_disabled_reason_without_twilio_fallback(setup):
    db, tenant, actor, binding = setup
    received = await receive(db, binding, content='STOP')
    sms = await db.get(SMSMessage, UUID(received['message_id']))
    thread = await db.get(MessageThread, sms.thread_id)
    tenant.sms_enabled = True
    tenant.sms_phone_number = '+1'+str(2000000000+uuid4().int % 7000000000)
    await db.commit()
    class Sender:
        ready = True
        mode = 'simulated'
    policy = (await comm.send_policy(db, tenant, thread, Sender()))[0]
    assert policy == {'can_send': False, 'reason': 'recipient_opted_out', 'max_length': 140}
    thread.inquiry_opted_out = False
    binding.enabled = False
    await db.commit()
    policy = (await comm.send_policy(db, tenant, thread, Sender()))[0]
    assert policy['can_send'] is False and policy['reason'] == 'callrail_binding_disabled'
    binding.enabled = True
    route = await db.scalar(select(CallRailConversation).where(CallRailConversation.thread_id == thread.id))
    route.selected_for_sending = False
    await db.commit()
    policy = (await comm.send_policy(db, tenant, thread, Sender()))[0]
    assert policy['can_send'] is False and policy['reason'] == 'callrail_binding_changed'
