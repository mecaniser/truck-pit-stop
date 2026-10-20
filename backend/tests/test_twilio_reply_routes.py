"""Dedicated reply-only DB; all contacts fictional and every provider call forbidden."""
import asyncio
import os
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4
import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI, HTTPException
from sqlalchemy import select, func, text
from sqlalchemy.exc import DBAPIError
from twilio.request_validator import RequestValidator
from app.db.models.twilio_reply_route import TwilioReplyRoute
from app.db.models.customer import Customer
from app.db.models.tenant import Tenant
from app.db.models.user import User
from app.db.models.message_thread import MessageThread
from app.db.models.sms_message import SMSMessage, SMSMessageDirection
from app.services import messaging_service as svc
from app.api.v1.endpoints import twilio_webhooks as web

pytestmark = pytest.mark.skipif(os.getenv('COMMUNICATIONS_ISOLATED_LOCAL') != '1', reason='isolated PostgreSQL only')


@pytest_asyncio.fixture
async def setup(monkeypatch):
    from app.db.session import AsyncSessionLocal, engine
    assert engine.url.database in {'twilio_reply_route_test_20261020', 'twilio_reply_route_gate_20261020'}
    assert engine.url.host in {'127.0.0.1', 'localhost'}
    assert engine.url.port == 55460 and engine.url.username == 'comms_local'
    for flag in ('SMS_TENANT_ROUTING_ENABLED','SMS_AUTOMATION_OUTBOX_ENABLED','SMS_RECOVERY_ENABLED'):
        if hasattr(web.routing.settings, flag):
            monkeypatch.setattr(web.routing.settings, flag, False)
    def forbidden(*a, **kw):
        pytest.fail('Provider access forbidden')
    monkeypatch.setattr(svc, '_get_twilio_client', forbidden)
    async def silent(**kw):
        pass
    monkeypatch.setattr(svc, 'broadcast_sms_message_event', silent)
    monkeypatch.setattr(svc, 'broadcast_sms_thread_event', silent)
    async with AsyncSessionLocal() as db:
        tenant = Tenant(name='Reply synthetic', slug='reply-'+uuid4().hex, is_active=True)
        db.add(tenant); await db.flush()
        phone = '+1500555'+str(uuid4().int % 10000).zfill(4)
        receiver = '+1500555'+str(uuid4().int % 10000).zfill(4)
        actor = User(tenant_id=tenant.id, first_name='Test', last_name='Owner', email=uuid4().hex+'@example.test',role='garage_owner',is_active=True)
        customer = Customer(tenant_id=tenant.id, first_name='Pinned',last_name='DBN', phone=phone,email=uuid4().hex+'@example.test')
        ets = Customer(tenant_id=tenant.id, first_name='Preserved',last_name='ETS', phone=phone,email=uuid4().hex+'@example.test')
        db.add_all([actor,customer,ets]);await db.flush()
        thread=MessageThread(tenant_id=tenant.id,customer_id=customer.id)
        other=MessageThread(tenant_id=tenant.id,customer_id=ets.id, last_message_preview='ETS history',unread_count_staff=7)
        db.add_all([thread,other]);await db.flush()
        now=datetime.now(timezone.utc)
        route=TwilioReplyRoute(tenant_id=tenant.id,customer_id=customer.id,thread_id=thread.id,
            approving_actor_id=actor.id,account_sid='AC'+uuid4().hex,to_number=receiver,from_number=phone,
            approval_reference='private-fixture-reference',approved_at=now-timedelta(minutes=1),expires_at=now+timedelta(hours=1),enabled=True)
        db.add(route);await db.commit()
        monkeypatch.setattr(web.routing.settings,'TWILIO_ACCOUNT_SID',route.account_sid)
        monkeypatch.setattr(web.routing.settings,'TWILIO_AUTH_TOKEN','synthetic-reply-token')
        yield SimpleNamespace(db=db, route=route, tenant=tenant, actor=actor,customer=customer,ets=ets,thread=thread,other=other)
        await db.rollback()
    await engine.dispose()


async def receive(s, **overrides):
    await s.db.refresh(s.route)
    values=dict(to_number=s.route.to_number,from_number=s.route.from_number,body='Synthetic reply',
        twilio_message_sid='SM'+uuid4().hex,authenticated_legacy_account_sid=s.route.account_sid)
    values.update(overrides)
    return await svc.handle_inbound_sms(s.db,**values)


@pytest.mark.asyncio
async def test_pin_duplicate_phone_stop_start_and_receipt(setup):
    s=setup; sid='SM'+uuid4().hex
    _,msg,c,duplicate=await receive(s,body='STOP',twilio_message_sid=sid)
    assert c.id==s.customer.id and c.sms_opt_out and not duplicate
    assert msg.twilio_reply_route_id==s.route.id and msg.twilio_account_sid==s.route.account_sid
    assert msg.binding_id is None
    _,again,_,duplicate=await receive(s,body='STOP',twilio_message_sid=sid)
    assert duplicate and again.id==msg.id
    await s.db.rollback()
    await receive(s,body='START')
    await s.db.refresh(s.customer);await s.db.refresh(s.ets);await s.db.refresh(s.other)
    assert s.customer.sms_opt_out and not s.ets.sms_opt_out
    assert s.other.unread_count_staff==7 and s.other.last_message_preview=='ETS history'
    assert s.thread.unread_count_staff==2


@pytest.mark.asyncio
@pytest.mark.parametrize('failure',['disabled','expired','revoked','deleted','phone','thread_deleted','customer_deleted','tenant_inactive','actor_inactive','actor_customer','foreign_actor','foreign_thread','foreign_customer'])
async def test_subject_and_history_fail_closed(setup,failure):
    s=setup
    if failure=='disabled':s.route.enabled=False
    elif failure=='expired':
        # New immutable approval with an already expired window, not editing approval identity.
        s.route.enabled=False;await s.db.flush()
        old=s.route
        s.route=TwilioReplyRoute(tenant_id=old.tenant_id,customer_id=old.customer_id,thread_id=old.thread_id,
            approving_actor_id=old.approving_actor_id,account_sid=old.account_sid,to_number=old.to_number,from_number=old.from_number,
            approval_reference='expired',approved_at=datetime.now(timezone.utc)-timedelta(hours=2),expires_at=datetime.now(timezone.utc)-timedelta(hours=1),enabled=True)
        s.db.add(s.route)
    elif failure=='revoked':s.route.revoked_at=datetime.now(timezone.utc)
    elif failure=='deleted':s.route.deleted_at=datetime.now(timezone.utc)
    elif failure=='phone':s.customer.phone='+15005550199'
    elif failure=='thread_deleted':s.thread.deleted_at=datetime.now(timezone.utc)
    elif failure=='customer_deleted':s.customer.deleted_at=datetime.now(timezone.utc)
    elif failure=='tenant_inactive':s.tenant.is_active=False
    elif failure=='actor_inactive':s.actor.is_active=False
    elif failure=='actor_customer':s.actor.role='customer'
    else:
        foreign=Tenant(name='Foreign',slug=uuid4().hex);s.db.add(foreign);await s.db.flush()
        {'foreign_actor':s.actor,'foreign_thread':s.thread,'foreign_customer':s.customer}[failure].tenant_id=foreign.id
    await s.db.commit()
    rid=s.route.id
    with pytest.raises(HTTPException) as exc:await receive(s)
    assert exc.value.status_code==409
    await s.db.rollback()
    assert await s.db.scalar(select(func.count()).select_from(SMSMessage).where(SMSMessage.twilio_reply_route_id==rid))==0


@pytest.mark.asyncio
@pytest.mark.parametrize('values',[{'authenticated_legacy_account_sid':None},{'authenticated_legacy_account_sid':'AC'+'f'*32},{'from_number':'+15005550999'},{'twilio_message_sid':None}])
async def test_reserved_receiver_never_guesses_or_creates_customer(setup,values):
    s=setup
    before=await s.db.scalar(select(func.count()).select_from(Customer))
    with pytest.raises(HTTPException):await receive(s,**values)
    await s.db.rollback()
    assert await s.db.scalar(select(func.count()).select_from(Customer))==before


@pytest.mark.asyncio
async def test_parallel_duplicates_one_message_one_unread(setup):
    from app.db.session import AsyncSessionLocal
    s=setup;sid='SM'+uuid4().hex
    to,fr,account,tid=s.route.to_number,s.route.from_number,s.route.account_sid,s.thread.id
    async def ingest():
        async with AsyncSessionLocal() as db:
            result=await svc.handle_inbound_sms(db,to_number=to,from_number=fr,body='Concurrent',twilio_message_sid=sid,authenticated_legacy_account_sid=account)
            return result[1].id
    ids=await asyncio.wait_for(asyncio.gather(*(ingest() for _ in range(4))),10)
    assert len(set(ids))==1
    await s.db.refresh(s.thread)
    assert s.thread.unread_count_staff==1


@pytest.mark.asyncio
@pytest.mark.parametrize('field',['direction','from_number','to_number','twilio_reply_route_id','customer_id','thread_id'])
async def test_conflicting_sid_is_not_duplicate_acceptance(setup,field):
    s=setup;sid='SM'+uuid4().hex
    _,msg,_,_=await receive(s,twilio_message_sid=sid)
    setattr(msg,field,{'direction':SMSMessageDirection.OUTBOUND,'from_number':'+15005550198','to_number':'+15005550197','twilio_reply_route_id':None,'customer_id':s.ets.id,'thread_id':s.other.id}[field])
    await s.db.commit()
    with pytest.raises(HTTPException) as exc:await receive(s,twilio_message_sid=sid)
    assert exc.value.status_code==409


@pytest.mark.asyncio
async def test_database_approval_is_immutable_and_history_cannot_be_erased(setup):
    s=setup
    rid=s.route.id
    s.route.to_number='+15005550188'
    with pytest.raises(DBAPIError):await s.db.commit()
    await s.db.rollback()
    with pytest.raises(DBAPIError):
        await s.db.execute(text('DELETE FROM twilio_reply_routes WHERE id=:id'),{'id':rid})
    await s.db.rollback()


@pytest.mark.asyncio
@pytest.mark.parametrize('auth',['valid','bad_signature','wrong_account','missing_account','wrong_from','wrong_to','missing_token','missing_signature','wrong_token'])
async def test_signed_public_endpoint(setup,auth,monkeypatch):
    from app.core.dependencies import get_db
    from app.db.session import AsyncSessionLocal
    s=setup
    app=FastAPI();app.include_router(web.router,prefix='/webhooks/twilio')
    async def dependency():
        async with AsyncSessionLocal() as db:yield db
    app.dependency_overrides[get_db]=dependency
    values=dict(AccountSid=s.route.account_sid,To=s.route.to_number,From=s.route.from_number,Body='Signed synthetic',MessageSid='SM'+uuid4().hex)
    if auth=='wrong_account':values['AccountSid']='AC'+'f'*32
    if auth=='missing_account':values.pop('AccountSid')
    if auth=='wrong_from':values['From']='+15005550999'
    if auth=='wrong_to':values['To']='+15005550998'
    url='https://example.test/webhooks/twilio/sms/inbound'
    signature=RequestValidator('synthetic-reply-token').compute_signature(url,values)
    if auth in {'missing_token','missing_signature','wrong_token'}:
        monkeypatch.setattr(web.routing.settings, 'ENVIRONMENT', 'development')
        if auth=='missing_token':monkeypatch.setattr(web.routing.settings,'TWILIO_AUTH_TOKEN','')
        if auth=='missing_signature':signature=''
        if auth=='wrong_token':signature=RequestValidator('wrong-token').compute_signature(url,values)
    if auth=='bad_signature':signature='wrong'
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='https://example.test') as client:
        response=await client.post(url,data=values,headers={'x-twilio-signature':signature})
    assert response.status_code==({'valid':200,'bad_signature':400,'wrong_account':400,'missing_account':409,'wrong_from':409,'wrong_to':404,'missing_token':400,'missing_signature':400,'wrong_token':400}[auth]),response.text


@pytest.mark.asyncio
@pytest.mark.parametrize('field,value',[('account_sid','unknown'),('to_number','(500) 555-0101'),('from_number','5005550101'),('approval_reference','  ')])
async def test_canonical_storage_required(setup,field,value):
    s=setup;r=s.route
    fields={name:getattr(r,name) for name in ['tenant_id','customer_id','thread_id','approving_actor_id','account_sid','to_number','from_number','approval_reference','approved_at','expires_at']}
    fields[field]=value
    s.db.add(TwilioReplyRoute(**fields))
    with pytest.raises(DBAPIError):await s.db.commit()
    await s.db.rollback()


@pytest.mark.asyncio
async def test_customer_lock_wait_crossing_expiry_rejected(setup,monkeypatch):
    from app.db.session import AsyncSessionLocal
    from app.services import twilio_reply_routes as routes
    s=setup
    clock=[datetime.now(timezone.utc)]
    class Clock:
        @staticmethod
        def now(tz):return clock[0]
    monkeypatch.setattr(routes,'datetime',Clock)
    reached=asyncio.Event()
    to,fr,account,cid=s.route.to_number,s.route.from_number,s.route.account_sid,s.customer.id
    expiry=s.route.expires_at
    async with AsyncSessionLocal() as blocker:
        await blocker.execute(select(Customer).where(Customer.id==cid).with_for_update())
        async def ingest():
            async with AsyncSessionLocal() as db:
                original=db.scalar
                async def scalar(statement,*args,**kwargs):
                    if 'FROM customers' in str(statement):reached.set()
                    return await original(statement,*args,**kwargs)
                db.scalar=scalar
                with pytest.raises(HTTPException) as exc:
                    await svc.handle_inbound_sms(db,to_number=to,from_number=fr,body='Expired during wait',
                        twilio_message_sid='SM'+uuid4().hex,authenticated_legacy_account_sid=account)
                assert exc.value.status_code==409
        task=asyncio.create_task(ingest())
        await asyncio.wait_for(reached.wait(),5)
        clock[0]=expiry+timedelta(seconds=1)
        await blocker.rollback()
        await asyncio.wait_for(task,5)
    assert await s.db.scalar(select(func.count()).select_from(SMSMessage).where(SMSMessage.twilio_reply_route_id==s.route.id))==0
