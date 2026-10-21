"""CallRail participates only in existing durable manual operations."""
import asyncio
import os
from uuid import uuid4
from datetime import datetime, timezone
import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy import select, func
from app.services import communications_service as svc, callrail_service as cr
from app.db.models.callrail import CallRailNumberBinding, CallRailConversation
from app.db.models.communication import SMSSendOperation
from app.db.models.sms_message import SMSMessage, SMSMessageSource, SMSMessageDirection, SMSDeliveryStatus
from app.db.models.user import User, UserRole
from app.db.models.customer import Customer
from app.db.models.message_thread import MessageThread
from app.db.models.tenant import Tenant
from app.api.v1.endpoints.communications import SendRequest

pytestmark = pytest.mark.skipif(os.getenv('COMMUNICATIONS_ISOLATED_LOCAL') != '1', reason='isolated PostgreSQL only')

@pytest_asyncio.fixture
async def setup(monkeypatch):
    from app.db.session import AsyncSessionLocal, engine
    async def allowed(*args, **kwargs): return True
    monkeypatch.setattr(svc, 'enforce_tenant_send_rate_limit', allowed)
    monkeypatch.setattr(svc.routing, 'enabled', lambda: False)
    async with AsyncSessionLocal() as db:
        tenant=Tenant(name='CallRail dispatch fixture',slug='crd-'+uuid4().hex,messaging_enabled=True,is_active=True,sms_enabled=False)
        db.add(tenant); await db.flush()
        actor=User(tenant_id=tenant.id,email=uuid4().hex+'@example.test',first_name='Synthetic',last_name='Staff',role=UserRole.GARAGE_OWNER,is_active=True)
        customer=Customer(tenant_id=tenant.id,first_name='Canonical',last_name='DBN',email=uuid4().hex+'@example.test',phone='+15005550002')
        duplicate=Customer(tenant_id=tenant.id,first_name='Preserved',last_name='ETS',email=uuid4().hex+'@example.test',phone='+15005550002')
        db.add_all([actor,customer,duplicate]); await db.flush()
        thread=MessageThread(tenant_id=tenant.id,customer_id=customer.id,customer_phone=customer.phone)
        binding=CallRailNumberBinding(tenant_id=tenant.id,account_id='ACC'+uuid4().hex,company_id='COMtest',tracker_id='TRKtest',sender_phone='+15005550001',credential_ref='CALLRAIL_TEST',signing_secret_ref='CALLRAIL_SIGNING',enabled=True)
        db.add_all([thread,binding]); await db.flush()
        db.add(CallRailConversation(tenant_id=tenant.id,thread_id=thread.id,customer_id=customer.id,customer_phone=customer.phone,binding_id=binding.id));await db.commit()
        db.add(SMSMessage(tenant_id=tenant.id,thread_id=thread.id,customer_id=customer.id,
            direction=SMSMessageDirection.INBOUND,source=SMSMessageSource.INBOUND,body='Proven reply fixture',
            from_number=customer.phone,to_number=binding.sender_phone,provider='callrail',provider_account_id=binding.account_id,
            callrail_binding_id=binding.id,provider_message_id='SCI'+uuid4().hex,delivery_status=SMSDeliveryStatus.DELIVERED))
        await db.commit()
        yield db,tenant,actor,customer,thread,binding
    await engine.dispose()

class TwilioMustNotSend:
    ready=False
    async def send(self, **kwargs): raise AssertionError('CallRail must not reach Twilio')

async def request_for(db,tenant,thread,body='manual test'):
    policy,account,identity,*_=await svc.send_policy(db,tenant,thread,TwilioMustNotSend())
    assert policy['can_send'] and policy['max_length']==140
    return SendRequest(channel_account_id=account,contact_identity_id=identity,body=body,expected_version=1)

@pytest.mark.asyncio
async def test_manual_replay_canonical_duplicate_and_receipt_race(setup,monkeypatch):
    db,tenant,actor,customer,thread,binding=setup
    thread_id=thread.id
    request=await request_for(db,tenant,thread)
    op,replay=await svc.create_operation(db,actor,tenant,thread.id,request,'once',TwilioMustNotSend())
    replay_op,replay=await svc.create_operation(db,actor,tenant,thread.id,request,'once',TwilioMustNotSend())
    assert replay and replay_op.id==op.id
    calls=[]
    async def fake(context,body,to):
        calls.append(body)
        from app.db.session import AsyncSessionLocal
        async with AsyncSessionLocal() as callback_db:
            await cr.apply_event(callback_db,binding.id,{'resource_id':'SCI'+uuid4().hex,'id':88543,'company_resource_id':binding.company_id,'conversation_id':'day1','source_number':binding.sender_phone,'destination_number':customer.phone,'content':body,'timestamp':datetime.now(timezone.utc).isoformat()},'sent')
            await callback_db.commit()
        raise TimeoutError('response lost after signed webhook')
    monkeypatch.setattr(cr,'send',fake)
    await svc.dispatch_operation(db,op.id,TwilioMustNotSend())
    await svc.dispatch_operation(db,op.id,TwilioMustNotSend())
    await db.refresh(op)
    sms=await db.get(SMSMessage,op.message_id)
    assert len(calls)==1 and op.state=='accepted' and op.provider_message_id
    assert sms.twilio_message_sid is None and sms.provider=='callrail'
    assert await db.scalar(select(func.count()).select_from(SMSMessage).where(SMSMessage.thread_id==thread_id))==2

@pytest.mark.asyncio
async def test_provider_limit_and_config_change_before_dispatch(setup,monkeypatch):
    db,tenant,actor,customer,thread,binding=setup
    too_long=await request_for(db,tenant,thread,'x'*141)
    with pytest.raises(HTTPException) as exc:
        await svc.create_operation(db,actor,tenant,thread.id,too_long,'length',TwilioMustNotSend())
    assert exc.value.status_code==422
    tenant_id,thread_id,actor_id,binding_id=tenant.id,thread.id,actor.id,binding.id
    await db.rollback()
    tenant=await db.get(Tenant,tenant_id);thread=await db.get(MessageThread,thread_id);actor=await db.get(User,actor_id)
    req=await request_for(db,tenant,thread)
    op,_=await svc.create_operation(db,actor,tenant,thread.id,req,'changed',TwilioMustNotSend())
    binding=await db.get(CallRailNumberBinding,binding_id);binding.company_id='COMchanged';await db.commit()
    async def must_not_send(*args): raise AssertionError('changed configuration reached provider')
    monkeypatch.setattr(cr,'send',must_not_send)
    await svc.dispatch_operation(db,op.id,TwilioMustNotSend());await db.refresh(op)
    assert op.state=='rejected' and op.attempt_count==0

@pytest.mark.asyncio
async def test_unknown_never_retried_and_automation_rejected(setup,monkeypatch):
    db,tenant,actor,customer,thread,binding=setup
    tenant_id,thread_id=tenant.id,thread.id
    req=await request_for(db,tenant,thread)
    op,_=await svc.create_operation(db,actor,tenant,thread.id,req,'unknown',TwilioMustNotSend())
    calls=[]
    async def timeout(*args): calls.append(1);raise TimeoutError('uncertain')
    monkeypatch.setattr(cr,'send',timeout)
    await svc.dispatch_operation(db,op.id,TwilioMustNotSend());await svc.dispatch_operation(db,op.id,TwilioMustNotSend());await db.refresh(op)
    assert op.state=='unknown' and calls==[1]
    tenant=await db.get(Tenant,tenant_id);thread=await db.get(MessageThread,thread_id)
    policy,*_=await svc.send_policy(db,tenant,thread,TwilioMustNotSend())
    assert policy['reason']=='ambiguous_outcome'

@pytest.mark.asyncio
async def test_http_success_preserves_provider_failure_receipt(setup,monkeypatch):
    db,tenant,actor,customer,thread,binding=setup
    req=await request_for(db,tenant,thread)
    op,_=await svc.create_operation(db,actor,tenant,thread.id,req,'failed-receipt',TwilioMustNotSend())
    async def fake(context,body,to):
        from app.db.session import AsyncSessionLocal
        async with AsyncSessionLocal() as callback_db:
            await cr.apply_event(callback_db,binding.id,{'resource_id':'SCI'+uuid4().hex,'id':88654,'company_resource_id':binding.company_id,'conversation_id':'day1','source_number':binding.sender_phone,'destination_number':customer.phone,'content':body,'timestamp':datetime.now(timezone.utc).isoformat()},'sent',failed=True)
            await callback_db.commit()
        return {'conversation_id':'day1'}
    monkeypatch.setattr(cr,'send',fake)
    await svc.dispatch_operation(db,op.id,TwilioMustNotSend())
    sms=await db.get(SMSMessage,op.message_id)
    await db.refresh(sms)
    assert sms.delivery_status.value=='failed'
