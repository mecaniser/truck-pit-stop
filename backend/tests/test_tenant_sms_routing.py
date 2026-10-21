"""Synthetic managed routing against the dedicated isolated PostgreSQL database."""
import asyncio
import json
import os
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4
import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy import select
from app.services import tenant_sms_routing as routing

pytestmark = pytest.mark.skipif(os.getenv('COMMUNICATIONS_ISOLATED_LOCAL') != '1', reason='dedicated isolated PostgreSQL required')

@pytest_asyncio.fixture(autouse=True)
async def managed(monkeypatch):
    monkeypatch.setattr(routing.settings, 'SMS_TENANT_ROUTING_ENABLED', True)
    yield
    from app.db.session import engine
    await engine.dispose()

async def seed(monkeypatch, *, consent=True):
    from app.db.session import AsyncSessionLocal
    from app.db.models.tenant import Tenant
    from app.db.models.customer import Customer
    from app.db.models.user import User
    from app.db.models.messaging_business import MessagingBusiness, TenantSMSBinding, SMSConsentEvidence
    tid,cid,uid,bid=uuid4(),uuid4(),uuid4(),uuid4()
    account='AC'+uuid4().hex; service='MG'+uuid4().hex; sender='+1'+str(2000000000+tid.int%7000000000)
    entries=json.loads(routing.settings.SMS_TENANT_CREDENTIALS_JSON)
    entries[str(tid)]={'account_sid':account,'auth_token':'synthetic-'+str(tid)}
    monkeypatch.setattr(routing.settings,'SMS_TENANT_CREDENTIALS_JSON',json.dumps(entries))
    async with AsyncSessionLocal() as db:
        db.add(Tenant(id=tid,name='Synthetic managed',slug='managed-'+str(tid),sms_enabled=True,messaging_enabled=True))
        await db.flush()
        db.add_all([Customer(id=cid,tenant_id=tid,first_name='Synthetic',last_name='Customer',email=str(cid)+'@example.test',phone='+15005550888'),User(id=uid,tenant_id=tid,first_name='Synthetic',last_name='Owner',email=str(uid)+'@example.test',hashed_password='disabled',role='garage_owner',is_active=True)])
        business=MessagingBusiness(tenant_id=tid,legal_name='Synthetic LLC');db.add(business);await db.flush()
        db.add(TenantSMSBinding(id=bid,tenant_id=tid,business_id=business.id,account_sid=account,customer_profile_sid='BU'+uuid4().hex,brand_sid='BN'+uuid4().hex,campaign_sid='QE'+uuid4().hex,messaging_service_sid=service,sender_sid='PN'+uuid4().hex,sender_phone=sender,credential_ref=str(tid),registration_status='approved',enabled=True,verified_at=datetime.now(timezone.utc),revision=1))
        if consent:
            db.add(SMSConsentEvidence(tenant_id=tid,recipient_kind='customer',recipient_id=cid,phone='+15005550888',purpose='service_notifications',status='granted',source='synthetic',disclosure_version='1',collected_at=datetime.now(timezone.utc),actor_id=uid))
        await db.commit()
    return SimpleNamespace(tid=tid,cid=cid,uid=uid,bid=bid,account=account,service=service,sender=sender)

class Sender:
    ready=True
    def __init__(self):self.calls=[]
    async def send(self,**kwargs):
        self.calls.append(kwargs)
        return {'sid':'SM'+uuid4().hex,'status':'queued'}

@pytest.mark.asyncio
async def test_two_accounts_dispatch_concurrent_replay_and_exact_snapshots(monkeypatch):
    from app.db.session import AsyncSessionLocal
    from app.services import automated_sms_service as auto
    a,b=await seed(monkeypatch),await seed(monkeypatch)
    sender=Sender()
    for shop in (a,b):
        async with AsyncSessionLocal() as db:
            op=await auto.enqueue_automated_sms(db,tenant_id=shop.tid,customer_id=shop.cid,domain_event_id='synthetic:1',template_name='work_started_sms',to='+15005550888',body='Synthetic message')
            await db.commit(); oid=op.id
            assert (op.binding_id,op.twilio_account_sid,op.messaging_service_sid,op.from_number)==(shop.bid,shop.account,shop.service,shop.sender)
        async def dispatch():
            async with AsyncSessionLocal() as db:await auto.dispatch_automated_operation(db,oid,sender)
        await asyncio.gather(dispatch(),dispatch())
    assert len(sender.calls)==2
    assert {x['routing_context'].account_sid for x in sender.calls}=={a.account,b.account}
    assert {x['routing_context'].messaging_service_sid for x in sender.calls}=={a.service,b.service}

@pytest.mark.asyncio
@pytest.mark.parametrize('change',['consent','binding','secret','disabled'])
async def test_dispatch_changes_fail_closed_without_provider_call(monkeypatch,change):
    from app.db.session import AsyncSessionLocal
    from app.db.models.messaging_business import SMSConsentEvidence,TenantSMSBinding
    from app.services import automated_sms_service as auto
    a=await seed(monkeypatch);sender=Sender()
    async with AsyncSessionLocal() as db:
        op=await auto.enqueue_automated_sms(db,tenant_id=a.tid,customer_id=a.cid,domain_event_id='synthetic:1',template_name='work_started_sms',to='+15005550888',body='Synthetic message');await db.commit();oid=op.id
        binding=await db.get(TenantSMSBinding,a.bid)
        if change=='consent':
            db.add(SMSConsentEvidence(tenant_id=a.tid,recipient_kind='customer',recipient_id=a.cid,phone='+15005550888',purpose='service_notifications',status='withdrawn',source='synthetic',disclosure_version='1',collected_at=datetime.now(timezone.utc),actor_id=a.uid))
        elif change=='binding':binding.retired_at=datetime.now(timezone.utc)
        elif change=='disabled':binding.enabled=False
        else:monkeypatch.setattr(routing.settings,'SMS_TENANT_CREDENTIALS_JSON','{}')
        await db.commit()
        assert await auto.dispatch_automated_operation(db,oid,sender)=='rejected'
    assert not sender.calls

@pytest.mark.asyncio
async def test_manual_and_legacy_select_managed_account(monkeypatch):
    from app.db.session import AsyncSessionLocal
    from app.db.models.user import User
    from app.services import messaging_service as messaging,communications_service as manual
    from app.db.models.customer import Customer
    a=await seed(monkeypatch);sender=Sender();provider_calls=[]
    monkeypatch.setattr(manual,'enforce_tenant_send_rate_limit',lambda *a,**k: asyncio.sleep(0,result=True))
    monkeypatch.setattr(routing,'client_for',lambda ctx:SimpleNamespace(messages=SimpleNamespace(create=lambda **p: provider_calls.append((ctx,p)) or SimpleNamespace(sid='SM'+uuid4().hex,status='queued'))))
    async with AsyncSessionLocal() as db:
        customer=await db.get(Customer,a.cid);thread=await messaging._get_or_create_thread(db,a.tid,customer);await db.commit()
        user=await db.get(User,a.uid);tenant=await manual.authorize(db,user)
        policy,account,identity,*_=await manual.send_policy(db,tenant,thread,sender)
        assert policy['can_send'] and account==a.bid
        op,_=await manual.create_operation(db,user,tenant,thread.id,SimpleNamespace(body='Manual synthetic',channel_account_id=account,contact_identity_id=identity,expected_version=1),'synthetic-key',sender)
        await manual.dispatch_operation(db,op.id,sender)
        await messaging.send_sms_with_tracking(db,a.tid,'+15005550888','Legacy synthetic',customer_id=a.cid,source='manual')
    assert sender.calls[0]['routing_context'].account_sid==a.account
    assert provider_calls[0][1]['messaging_service_sid']==a.service
    assert provider_calls[0][1]['from_']==a.sender

@pytest.mark.asyncio
async def test_signed_account_routing_and_historical_receipt(monkeypatch):
    from app.db.session import AsyncSessionLocal
    from app.db.models.messaging_business import TenantSMSBinding
    from app.services import messaging_service as messaging,automated_sms_service as auto
    a,b=await seed(monkeypatch),await seed(monkeypatch)
    async with AsyncSessionLocal() as db:
        assert await routing.account_token(db,a.account)!=await routing.account_token(db,b.account)
        with pytest.raises(HTTPException):await routing.inbound_binding(db,a.account,b.sender)
        op=await auto.enqueue_automated_sms(db,tenant_id=a.tid,customer_id=a.cid,domain_event_id='synthetic:1',template_name='work_started_sms',to='+15005550888',body='Synthetic');await db.commit()
        await auto.dispatch_automated_operation(db,op.id,Sender())
        await db.refresh(op);sid=op.provider_message_sid
        binding=await db.get(TenantSMSBinding,a.bid);binding.retired_at=datetime.now(timezone.utc);await db.commit()
        assert await routing.account_token(db,a.account)
        with pytest.raises(HTTPException):await messaging.process_twilio_status_callback(db,message_sid=sid,message_status='delivered',account_sid=b.account)
        await db.rollback()
        sms=await messaging.process_twilio_status_callback(db,message_sid=sid,message_status='delivered',account_sid=a.account,from_number=a.sender,messaging_service_sid=a.service)
        assert sms.delivery_status.value=='delivered'

@pytest.mark.asyncio
async def test_stop_one_tenant_and_start_never_grants_consent(monkeypatch):
    from app.db.session import AsyncSessionLocal
    from app.db.models.customer import Customer
    from app.services import messaging_service as messaging
    a,b=await seed(monkeypatch),await seed(monkeypatch)
    async with AsyncSessionLocal() as db:
        sid='SM'+uuid4().hex
        _,msg,_,_=await messaging.handle_inbound_sms(db,to_number=a.sender,from_number='+15005550888',body='STOP',twilio_message_sid=sid,account_sid=a.account)
        _,duplicate,_,replayed=await messaging.handle_inbound_sms(db,to_number=a.sender,from_number='+15005550888',body='STOP',twilio_message_sid=sid,account_sid=a.account)
        assert replayed and duplicate.id==msg.id
        await messaging.handle_inbound_sms(db,to_number=a.sender,from_number='+15005550888',body='START',twilio_message_sid='SM'+uuid4().hex,account_sid=a.account)
        assert (await db.get(Customer,a.cid)).sms_opt_out
        assert not (await db.get(Customer,b.cid)).sms_opt_out

@pytest.mark.asyncio
async def test_staff_and_tenant_contact_require_their_own_consent(monkeypatch):
    from app.db.session import AsyncSessionLocal
    from app.db.models.user import User
    from app.db.models.tenant import Tenant
    from app.db.models.messaging_business import SMSConsentEvidence
    from app.services import automated_sms_service as auto
    a=await seed(monkeypatch);sender=Sender()
    async with AsyncSessionLocal() as db:
        user=await db.get(User,a.uid);user.phone='+15005550888'
        tenant=await db.get(Tenant,a.tid);tenant.phone='+15005550888';await db.commit()
        for kind in ('user','tenant_contact'):
            kwargs={'recipient_user_id':a.uid} if kind=='user' else {'recipient_tenant_contact':True}
            payload=dict(tenant_id=a.tid,domain_event_id='staff-synthetic:'+kind,template_name='quote_declined_shop',to='+15005550888',body='Synthetic staff',**kwargs)
            with pytest.raises(HTTPException) as exc:await auto.enqueue_automated_sms(db,**payload)
            assert exc.value.detail['code']=='consent_required';await db.rollback()
            db.add(SMSConsentEvidence(tenant_id=a.tid,recipient_kind=kind,recipient_id=a.uid if kind=='user' else a.tid,phone='+15005550888',purpose='service_notifications',status='granted',source='synthetic',disclosure_version='1',collected_at=datetime.now(timezone.utc),actor_id=a.uid));await db.commit()
            op=await auto.enqueue_automated_sms(db,**payload);await db.commit()
            assert await auto.dispatch_automated_operation(db,op.id,sender)=='accepted'
    assert len(sender.calls)==2
    assert all(call['routing_context'].account_sid==a.account for call in sender.calls)

@pytest.mark.asyncio
async def test_managed_signature_uses_routed_account_token(monkeypatch):
    from app.db.session import AsyncSessionLocal
    from app.api.v1.endpoints import twilio_webhooks as webhooks
    from starlette.requests import Request
    from twilio.request_validator import RequestValidator
    a,b=await seed(monkeypatch),await seed(monkeypatch)
    request=Request({'type':'http','method':'POST','scheme':'https','server':('test.example',443),'path':'/sms/inbound','raw_path':b'/sms/inbound','query_string':b'','headers':[(b'host',b'test.example')]})
    async with AsyncSessionLocal() as db:
        values={'AccountSid':a.account,'To':a.sender,'From':'+15005550888','Body':'Synthetic'}
        token=await routing.account_token(db,a.account)
        signature=RequestValidator(token).compute_signature(str(request.url),values)
        assert await webhooks._signature_for_account(db,request,values,signature)
        forged=dict(values,AccountSid=b.account)
        assert not await webhooks._signature_for_account(db,request,forged,signature)
        wrong=RequestValidator(await routing.account_token(db,b.account)).compute_signature(str(request.url),values)
        assert not await webhooks._signature_for_account(db,request,values,wrong)
        assert not await webhooks._signature_for_account(db,request,dict(values,AccountSid='ACunknown'),signature)
        assert not await webhooks._signature_for_account(db,request,{'To':a.sender},signature)

@pytest.mark.asyncio
async def test_live_adapter_requires_managed_context_and_exact_service(monkeypatch):
    from app.services.communications_service import LiveSMSSender
    context=routing.SMSContext(uuid4(),'AC'+uuid4().hex,'MG'+uuid4().hex,'+15005550001','synthetic')
    calls=[]
    monkeypatch.setattr(routing,'client_for',lambda ctx:SimpleNamespace(messages=SimpleNamespace(create=lambda **payload:calls.append((ctx,payload)) or SimpleNamespace(sid='SMsynthetic',status='queued'))))
    with pytest.raises(HTTPException):await LiveSMSSender().send(body='Synthetic',from_number=context.sender_phone,to_number='+15005550888',status_callback=None)
    result=await LiveSMSSender().send(body='Synthetic',from_number=context.sender_phone,to_number='+15005550888',status_callback=None,routing_context=context)
    assert result['sid']=='SMsynthetic'
    assert calls==[(context,{'body':'Synthetic','from_':context.sender_phone,'to':'+15005550888','messaging_service_sid':context.messaging_service_sid})]

@pytest.mark.asyncio
async def test_parallel_inbound_dedup_is_account_scoped(monkeypatch):
    from app.db.session import AsyncSessionLocal
    from app.services import messaging_service as messaging
    a,b=await seed(monkeypatch),await seed(monkeypatch);sid='SM'+uuid4().hex
    async def receive(shop):
        async with AsyncSessionLocal() as db:
            _,message,_,_=await messaging.handle_inbound_sms(db,to_number=shop.sender,from_number='+15005550888',body='Synthetic reply',twilio_message_sid=sid,account_sid=shop.account)
            mid=message.id;await db.commit();return mid
    first=await asyncio.gather(*(receive(a) for _ in range(4)))
    assert len(set(first))==1
    assert await receive(b)!=first[0]

@pytest.mark.asyncio
async def test_rollout_disable_rejects_persisted_managed_pending_operations(monkeypatch):
    from app.db.session import AsyncSessionLocal
    from app.db.models.tenant import Tenant
    from app.db.models.user import User
    from app.db.models.customer import Customer
    from app.services import communications_service as manual,automated_sms_service as auto,messaging_service as messaging
    a=await seed(monkeypatch);sender=Sender()
    monkeypatch.setattr(manual,'enforce_tenant_send_rate_limit',lambda *a,**k:asyncio.sleep(0,result=True))
    monkeypatch.setattr(manual,'_get_twilio_client',lambda:pytest.fail('No global provider fallback permitted'))
    async with AsyncSessionLocal() as db:
        tenant=await db.get(Tenant,a.tid);tenant.sms_phone_number=a.sender
        user=await db.get(User,a.uid);customer=await db.get(Customer,a.cid)
        thread=await messaging._get_or_create_thread(db,a.tid,customer);await db.commit()
        _,account,identity,*_=await manual.send_policy(db,tenant,thread,sender)
        op,_=await manual.create_operation(db,user,tenant,thread.id,SimpleNamespace(body='Synthetic manual',channel_account_id=account,contact_identity_id=identity,expected_version=1),'rollback-test',sender)
        manual_id=op.id
        automated=await auto.enqueue_automated_sms(db,tenant_id=a.tid,customer_id=a.cid,domain_event_id='rollback-test:1',template_name='work_started_sms',to='+15005550888',body='Synthetic automated');await db.commit();auto_id=automated.id
        monkeypatch.setattr(routing.settings,'SMS_TENANT_ROUTING_ENABLED',False)
        await manual.dispatch_operation(db,manual_id,sender)
        assert await auto.dispatch_automated_operation(db,auto_id,sender)=='rejected'
        await db.refresh(op);await db.refresh(automated)
        assert op.error_code==automated.error_code=='routing_disabled'
    assert not sender.calls

@pytest.mark.asyncio
async def test_rollout_disable_preserves_managed_callback_authentication(monkeypatch):
    from app.db.session import AsyncSessionLocal
    from app.db.models.sms_message import SMSMessage
    from app.services import messaging_service as messaging,automated_sms_service as auto
    from app.api.v1.endpoints import twilio_webhooks as webhooks
    from starlette.requests import Request
    from twilio.request_validator import RequestValidator
    a=await seed(monkeypatch)
    async with AsyncSessionLocal() as db:
        op=await auto.enqueue_automated_sms(db,tenant_id=a.tid,customer_id=a.cid,domain_event_id='rollback-receipt:1',template_name='work_started_sms',to='+15005550888',body='Synthetic');await db.commit();await auto.dispatch_automated_operation(db,op.id,Sender());await db.refresh(op)
        sid=op.provider_message_sid;mid=op.message_id
        token=await routing.account_token(db,a.account)
        monkeypatch.setattr(routing.settings,'SMS_TENANT_ROUTING_ENABLED',False)
        monkeypatch.setattr(routing.settings,'TWILIO_AUTH_TOKEN','synthetic-global-token')
        request=Request({'type':'http','method':'POST','scheme':'https','server':('test.example',443),'path':'/sms/status','raw_path':b'/sms/status','query_string':b'','headers':[(b'host',b'test.example')]})
        values={'AccountSid':a.account,'MessageSid':sid,'MessageStatus':'delivered'}
        wrong=RequestValidator('synthetic-global-token').compute_signature(str(request.url),values)
        assert not await webhooks._signature_for_account(db,request,values,wrong)
        signature=RequestValidator(token).compute_signature(str(request.url),values)
        assert await webhooks._signature_for_account(db,request,values,signature)
        # Legacy/global service calls cannot select any managed row without its account.
        await messaging.process_twilio_status_callback(db,message_sid=sid,message_status='failed')
        await db.refresh(op)
        sms=await db.get(SMSMessage,mid);await db.refresh(sms)
        assert sms.delivery_status.value=='queued' and op.delivery_status=='queued'
        sms=await messaging.process_twilio_status_callback(db,message_sid=sid,message_status='delivered',account_sid=a.account,from_number=a.sender,messaging_service_sid=a.service)
        assert sms.delivery_status.value=='delivered'

@pytest.mark.asyncio
async def test_rollout_disable_blocks_new_sends_for_previously_managed_tenant(monkeypatch):
    from app.db.session import AsyncSessionLocal
    from app.db.models.tenant import Tenant
    from app.db.models.customer import Customer
    from app.services import communications_service as manual,automated_sms_service as auto,messaging_service as messaging
    a=await seed(monkeypatch);sender=Sender()
    monkeypatch.setattr(routing.settings,'SMS_TENANT_ROUTING_ENABLED',False)
    monkeypatch.setattr(messaging,'_get_twilio_client',lambda:pytest.fail('Global provider cannot be used by onboarded shop'))
    async with AsyncSessionLocal() as db:
        tenant=await db.get(Tenant,a.tid);tenant.sms_phone_number=a.sender
        thread=await messaging._get_or_create_thread(db,a.tid,await db.get(Customer,a.cid));await db.commit()
        policy,*_=await manual.send_policy(db,tenant,thread,sender)
        assert policy=={'can_send':False,'reason':'reply_route_unavailable'}
        with pytest.raises(HTTPException) as exc:await auto.enqueue_automated_sms(db,tenant_id=a.tid,customer_id=a.cid,domain_event_id='rollback-new:1',template_name='work_started_sms',to='+15005550888',body='Synthetic')
        assert exc.value.detail['code']=='routing_disabled';await db.rollback()
        with pytest.raises(HTTPException) as exc:await messaging.send_sms_with_tracking(db,a.tid,'+15005550888','Synthetic',customer_id=a.cid,source='manual')
        assert exc.value.detail['code']=='routing_disabled';await db.rollback()
        with pytest.raises(HTTPException):await messaging.handle_inbound_sms(db,to_number=a.sender,from_number='+15005550888',body='STOP',twilio_message_sid='SM'+uuid4().hex)

@pytest.mark.asyncio
@pytest.mark.parametrize('sid',[None,'','   '])
async def test_managed_inbound_requires_receipt_identity_before_mutation(monkeypatch,sid):
    from app.db.session import AsyncSessionLocal
    from app.services import messaging_service as messaging
    from app.db.models.customer import Customer
    from app.db.models.sms_message import SMSMessage
    from sqlalchemy import func
    a=await seed(monkeypatch)
    async with AsyncSessionLocal() as db:
        before=await db.scalar(select(func.count()).select_from(SMSMessage).where(SMSMessage.tenant_id==a.tid))
        with pytest.raises(HTTPException) as exc:await messaging.handle_inbound_sms(db,to_number=a.sender,from_number='+15005550888',body='STOP',twilio_message_sid=sid,account_sid=a.account)
        assert exc.value.status_code==400
        assert not (await db.get(Customer,a.cid)).sms_opt_out
        assert await db.scalar(select(func.count()).select_from(SMSMessage).where(SMSMessage.tenant_id==a.tid))==before
