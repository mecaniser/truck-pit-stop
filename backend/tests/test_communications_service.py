"""Real PostgreSQL acceptance, opt-in against the dedicated synthetic inbox only."""
import asyncio
import os
from datetime import datetime, timezone, timedelta
from uuid import uuid4
import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy import select, func

pytestmark = pytest.mark.skipif(os.getenv('COMMUNICATIONS_ISOLATED_LOCAL') != '1', reason='requires dedicated isolated PostgreSQL')


@pytest_asyncio.fixture(autouse=True)
async def isolated_engine_lifecycle(monkeypatch):
    if os.getenv('COMMUNICATIONS_ISOLATED_LOCAL') != '1':
        yield
        return
    from app.db.session import engine
    from app.services import communications_service as svc
    async def allowed(*args, **kwargs):
        return True
    monkeypatch.setattr(svc, 'enforce_tenant_send_rate_limit', allowed)
    yield
    await engine.dispose()


@pytest.mark.asyncio
async def test_durable_operation_concurrency_and_unknown_recovery():
    from app.db.session import AsyncSessionLocal
    from app.db.models.tenant import Tenant
    from app.db.models.user import User
    from app.db.models.customer import Customer
    from app.db.models.message_thread import MessageThread
    from app.db.models.sms_message import SMSMessage
    from app.db.models.communication import SMSSendOperation
    from app.api.v1.endpoints.communications import SendRequest
    from app.services import communications_service as svc
    tenant_id, actor_id, customer_id, thread_id = [uuid4() for _ in range(4)]
    class Sender:
        mode = 'simulated'
        calls = 0
        unknown = False
        async def send(self, **kwargs):
            self.calls += 1
            if self.unknown:
                raise TimeoutError()
            return {'sid': f'SM{uuid4().hex}', 'status': 'queued'}
    sender = Sender()
    async with AsyncSessionLocal() as db:
        tenant = Tenant(id=tenant_id, name='Operation test', slug=f'op-{tenant_id}', sms_enabled=True, messaging_enabled=True, sms_phone_number='+1' + str(2000000000 + tenant_id.int % 7000000000))
        db.add(tenant)
        await db.flush()
        actor = User(id=actor_id, tenant_id=tenant_id, first_name='Test', last_name='Operator', email=f'{actor_id}@example.test', hashed_password='disabled', role='garage_owner', is_active=True)
        customer = Customer(id=customer_id, tenant_id=tenant_id, first_name='Test', last_name='Customer', email=f'{customer_id}@example.test', phone='+15005550888')
        db.add_all([actor, customer]); await db.flush()
        thread = MessageThread(id=thread_id, tenant_id=tenant_id, customer_id=customer_id)
        db.add(thread); await db.commit()
        policy, account, identity, *_ = await svc.send_policy(db, tenant, thread, sender)
        assert policy['can_send']
    request = SendRequest(channel_account_id=account, contact_identity_id=identity, body='One send', expected_version=1)
    key = uuid4().hex
    async def create():
        async with AsyncSessionLocal() as db:
            tenant = await db.get(Tenant, tenant_id); actor = await db.get(User, actor_id)
            op, replayed = await svc.create_operation(db, actor, tenant, thread_id, request, key, sender)
            await db.commit()
            return op.id, replayed
    results = await asyncio.gather(create(), create(), create())
    assert len({r[0] for r in results}) == 1
    assert sum(not r[1] for r in results) == 1
    operation_id = results[0][0]
    async def dispatch():
        async with AsyncSessionLocal() as db:
            await svc.dispatch_operation(db, operation_id, sender)
    async def recover_pending():
        async with AsyncSessionLocal() as db:
            await svc.process_pending_operations(db, sender, tenant_id=tenant_id)
    await asyncio.gather(dispatch(), recover_pending())
    assert sender.calls == 1
    async with AsyncSessionLocal() as db:
        op = await db.get(SMSSendOperation, operation_id)
        assert op.state == 'accepted' and op.attempt_count == 1
        assert await db.scalar(select(func.count()).select_from(SMSMessage).where(SMSMessage.thread_id == thread_id)) == 1
        tenant = await db.get(Tenant, tenant_id); actor = await db.get(User, actor_id)
        conflict = request.model_copy(update={'body': 'Changed payload'})
        with pytest.raises(HTTPException) as error:
            await svc.create_operation(db, actor, tenant, thread_id, conflict, key, sender)
        assert error.value.detail['code'] == 'idempotency_conflict'
        await db.rollback()
    async with AsyncSessionLocal() as db:
        tenant = await db.get(Tenant, tenant_id); actor = await db.get(User, actor_id)
        second = request.model_copy(update={'body': 'Ambiguous send', 'expected_version': 2})
        op, _ = await svc.create_operation(db, actor, tenant, thread_id, second, uuid4().hex, sender)
        unknown_id = op.id
    sender.unknown = True
    async with AsyncSessionLocal() as db:
        await svc.dispatch_operation(db, unknown_id, sender)
        await svc.dispatch_operation(db, unknown_id, sender)
        op = await db.get(SMSSendOperation, unknown_id)
        assert op.state == 'unknown' and op.reconciliation_state == 'required' and op.attempt_count == 1
        assert sender.calls == 2
        tenant = await db.get(Tenant, tenant_id); thread = await db.get(MessageThread, thread_id)
        policy, *_ = await svc.send_policy(db, tenant, thread, sender)
        assert policy['reason'] == 'ambiguous_outcome'
        # Simulate crash after committed claim; bounded recovery holds, never sends.
        op.state = 'dispatching'; op.dispatch_started_at = datetime.now(timezone.utc) - timedelta(minutes=6)
        await db.commit()
        await svc.process_pending_operations(db, sender, tenant_id=tenant_id)
        await db.refresh(op)
        assert op.state == 'unknown' and sender.calls == 2


@pytest.mark.asyncio
@pytest.mark.parametrize('change', ['opt_out', 'disabled', 'actor_revoked', 'sender_changed', 'recipient_changed', 'shared_phone', 'customer_deleted', 'thread_deleted'])
async def test_pending_rechecks_before_provider_attempt(change):
    from app.db.session import AsyncSessionLocal
    from app.db.models.tenant import Tenant
    from app.db.models.user import User
    from app.db.models.customer import Customer
    from app.db.models.message_thread import MessageThread
    from app.db.models.communication import SMSSendOperation
    from app.api.v1.endpoints.communications import SendRequest
    from app.services import communications_service as svc
    tenant_id, actor_id, customer_id, thread_id = [uuid4() for _ in range(4)]
    class Sender:
        mode = 'simulated'
        calls = 0
        async def send(self, **kwargs):
            self.calls += 1
            return {'sid': f'SM{uuid4().hex}', 'status': 'queued'}
    sender = Sender()
    async with AsyncSessionLocal() as db:
        tenant = Tenant(id=tenant_id, name='Gate test', slug=f'op-{tenant_id}', sms_enabled=True, messaging_enabled=True, sms_phone_number='+1' + str(2000000000 + tenant_id.int % 7000000000))
        db.add(tenant); await db.flush()
        actor = User(id=actor_id, tenant_id=tenant_id, first_name='Test', last_name='Operator', email=f'{actor_id}@example.test', hashed_password='disabled', role='garage_owner', is_active=True)
        customer = Customer(id=customer_id, tenant_id=tenant_id, first_name='Test', last_name='Customer', email=f'{customer_id}@example.test', phone='+15005550888')
        db.add_all([actor, customer]); await db.flush()
        thread = MessageThread(id=thread_id, tenant_id=tenant_id, customer_id=customer_id)
        db.add(thread); await db.commit()
        _, account, identity, *_ = await svc.send_policy(db, tenant, thread, sender)
        request = SendRequest(channel_account_id=account, contact_identity_id=identity, body='Held until checked', expected_version=1)
        op, _ = await svc.create_operation(db, actor, tenant, thread_id, request, uuid4().hex, sender)
        operation_id = op.id
        if change == 'opt_out':
            customer.sms_opt_out = True
        elif change == 'disabled':
            tenant.messaging_enabled = False
        elif change == 'actor_revoked':
            actor.is_active = False
        elif change == 'sender_changed':
            tenant.sms_phone_number = '+1' + str(2000000000 + uuid4().int % 7000000000)
        elif change == 'recipient_changed':
            customer.phone = '+15005550887'
        elif change == 'customer_deleted':
            customer.deleted_at = datetime.now(timezone.utc)
        elif change == 'thread_deleted':
            thread.deleted_at = datetime.now(timezone.utc)
        else:
            db.add(Customer(tenant_id=tenant_id, first_name='Another', last_name='Customer', email=f'{uuid4()}@example.test', phone=customer.phone))
        await db.commit()
    # A fresh session models restart recovery from the durable pending operation.
    async with AsyncSessionLocal() as db:
        await svc.dispatch_operation(db, operation_id, sender)
        op = await db.get(SMSSendOperation, operation_id)
        assert op.state == 'rejected' and op.attempt_count == 0
        assert sender.calls == 0


@pytest.mark.asyncio
async def test_inbound_normalized_identity_and_duplicate_receipt(monkeypatch):
    from app.db.session import AsyncSessionLocal
    from app.db.models.tenant import Tenant
    from app.db.models.customer import Customer
    from app.db.models.message_thread import MessageThread
    from app.db.models.sms_message import SMSMessage
    from app.db.models.communication import ConversationWorkflow
    from app.services import messaging_service as svc
    async def no_broadcast(**kwargs):
        pass
    monkeypatch.setattr(svc, 'broadcast_sms_message_event', no_broadcast)
    monkeypatch.setattr(svc, 'broadcast_sms_thread_event', no_broadcast)
    tenant_id, customer_id, thread_id = [uuid4() for _ in range(3)]
    sender = '+1' + str(2000000000 + tenant_id.int % 7000000000)
    async with AsyncSessionLocal() as db:
        db.add(Tenant(id=tenant_id, name='Inbound test', slug=f'in-{tenant_id}', sms_enabled=True, sms_phone_number=sender))
        await db.flush()
        db.add(Customer(id=customer_id, tenant_id=tenant_id, first_name='Original', last_name='Customer', email=f'{customer_id}@example.test', phone='+15005550888'))
        await db.flush()
        db.add(MessageThread(id=thread_id, tenant_id=tenant_id, customer_id=customer_id, customer_phone='+15005550888'))
        await db.flush()
        db.add(ConversationWorkflow(tenant_id=tenant_id, thread_id=thread_id, status='resolved', version=2))
        await db.commit()
    sid = 'SM' + uuid4().hex
    async def receive():
        async with AsyncSessionLocal() as db:
            thread, sms, customer, replay = await svc.handle_inbound_sms(db, to_number=sender, from_number='+1 (500) 555-0888', body='Reply', twilio_message_sid=sid)
            return thread.id, customer.id, replay
    results = await asyncio.gather(receive(), receive())
    assert all(r[:2] == (thread_id, customer_id) for r in results)
    assert sorted(r[2] for r in results) == [False, True]
    async with AsyncSessionLocal() as db:
        assert await db.scalar(select(func.count()).select_from(SMSMessage).where(SMSMessage.thread_id == thread_id)) == 1
        wf = await db.scalar(select(ConversationWorkflow).where(ConversationWorkflow.thread_id == thread_id))
        assert wf.status == 'open' and wf.version == 3
        db.add(Customer(tenant_id=tenant_id, first_name='Shared', last_name='Phone', email=f'{uuid4()}@example.test', phone='5005550888'))
        await db.commit()
        with pytest.raises(HTTPException) as error:
            await svc.handle_inbound_sms(db, to_number=sender, from_number='+15005550888', body='Ambiguous', twilio_message_sid='SM'+uuid4().hex)
        assert error.value.status_code == 409
    # Two distinct inbound SIDs for a previously unknown identity share one customer.
    async def receive_unknown():
        async with AsyncSessionLocal() as db:
            t, m, c, replay = await svc.handle_inbound_sms(db, to_number=sender, from_number='+15005550889', body='New sender', twilio_message_sid='SM'+uuid4().hex)
            return c.id, t.id
    identities = await asyncio.gather(receive_unknown(), receive_unknown())
    assert identities[0] == identities[1]
    async with AsyncSessionLocal() as db:
        created_workflow = await db.scalar(select(ConversationWorkflow).where(ConversationWorkflow.thread_id == identities[0][1]))
        assert created_workflow.version == 3
        from app.services import communications_service as inbox
        customer = await db.get(Customer, customer_id)
        customer.deleted_at = datetime.now(timezone.utc)
        await db.commit()
        with pytest.raises(HTTPException) as error:
            await inbox.thread_for(db, tenant_id, thread_id)
        assert error.value.status_code == 404
