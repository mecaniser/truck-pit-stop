"""Synthetic automatic-route evidence; no provider credentials or network."""
from datetime import datetime, timezone, timedelta
from uuid import uuid4
import pytest
from sqlalchemy import select, func
from fastapi import HTTPException
from app.services import automatic_sms_route as routes, communications_service as svc, callrail_service as cr
from app.db.models.sms_message import SMSMessage, SMSMessageDirection as Direction, SMSMessageSource as Source, SMSDeliveryStatus as Status
from app.db.models.callrail import CallRailNumberBinding, CallRailConversation
from app.db.models.communication import ConversationWorkflow
from app.api.v1.endpoints.communications import patch_sender, SenderPatch
from test_callrail_dispatch import setup, TwilioMustNotSend, request_for


@pytest.fixture(autouse=True)
def isolated_database():
    from app.db.session import engine
    assert engine.url.database in {'auto_reply_routes_20261020','auto_reply_routes_gate_20261020'}
    assert engine.url.host in {'127.0.0.1','localhost'} and engine.url.port==55460 and engine.url.username=='comms_local'


async def add(db,tenant,customer,thread,binding=None,*,inbound=True,when=None,**kwargs):
    values=dict(tenant_id=tenant.id,customer_id=customer.id,thread_id=thread.id,
        direction=Direction.INBOUND if inbound else Direction.OUTBOUND,source=Source.INBOUND if inbound else Source.MANUAL,
        body='Synthetic route evidence',from_number=customer.phone if inbound else binding.sender_phone if binding else tenant.sms_phone_number,
        to_number=binding.sender_phone if binding else tenant.sms_phone_number if inbound else customer.phone,
        created_at=when or datetime.now(timezone.utc),delivery_status=Status.DELIVERED)
    if not inbound:values['to_number']=customer.phone
    if binding:values.update(provider='callrail',provider_account_id=binding.account_id,callrail_binding_id=binding.id,provider_message_id='SCI'+uuid4().hex)
    else:values.update(twilio_message_sid='SM'+uuid4().hex)
    values.update(kwargs)
    row=SMSMessage(**values);db.add(row);await db.commit();return row


@pytest.mark.asyncio
async def test_mixed_history_uses_latest_inbound_both_directions_and_delay(setup):
    db,tenant,actor,c,t,b=setup
    tenant.sms_phone_number='+1500555'+str(uuid4().int%10000).zfill(4);tenant.sms_enabled=True;await db.commit()
    now=datetime.now(timezone.utc)
    await add(db,tenant,c,t,when=now)
    assert (await routes.resolve(db,tenant,t,c.phone)).provider=='twilio'
    await add(db,tenant,c,t,b,when=now+timedelta(seconds=2))
    assert (await routes.resolve(db,tenant,t,c.phone)).callrail.binding_id==b.id
    await add(db,tenant,c,t,when=now-timedelta(days=1))
    assert (await routes.resolve(db,tenant,t,c.phone)).provider=='callrail'


@pytest.mark.asyncio
async def test_selection_flag_cannot_override_receiving_binding(setup):
    db,tenant,actor,c,t,b=setup
    mapping=await db.scalar(select(CallRailConversation).where(CallRailConversation.thread_id==t.id))
    mapping.selected_for_sending=False
    alternative=CallRailNumberBinding(tenant_id=tenant.id,account_id=b.account_id,company_id=b.company_id,
        tracker_id=b.tracker_id,sender_phone='+15005550111',enabled=True,credential_ref='CALLRAIL_TEST',signing_secret_ref='CALLRAIL_SIGNING')
    db.add(alternative);await db.flush()
    db.add(CallRailConversation(tenant_id=tenant.id,customer_id=c.id,thread_id=t.id,binding_id=alternative.id,customer_phone=c.phone,selected_for_sending=True));await db.commit()
    result=await routes.resolve(db,tenant,t,c.phone)
    assert result.callrail.binding_id==b.id
    context=await cr.sender_context(db,tenant,t)
    assert context['sender_selection_allowed'] is False and context['sender_mode']=='reply'
    assert context['sender_number']==b.sender_phone and 'sms_sender_options' not in context


@pytest.mark.asyncio
@pytest.mark.parametrize('failure',['disabled','foreign','malformed','wrong_remote','wrong_sender','wrong_account'])
async def test_newest_invalid_evidence_does_not_fall_back(setup,failure):
    db,tenant,actor,c,t,b=setup
    row=await add(db,tenant,c,t,b)
    if failure=='disabled':b.enabled=False
    elif failure=='foreign':
        from app.db.models.tenant import Tenant
        foreign=Tenant(name='Foreign synthetic',slug=uuid4().hex);db.add(foreign);await db.flush()
        foreign_binding=CallRailNumberBinding(tenant_id=foreign.id,account_id='ACC'+uuid4().hex,company_id='COMforeign',
            tracker_id='TRKforeign',sender_phone='+15005550117',enabled=True,credential_ref='CALLRAIL_TEST',signing_secret_ref='CALLRAIL_SIGNING')
        db.add(foreign_binding);await db.flush();row.callrail_binding_id=foreign_binding.id
    elif failure=='malformed':row.provider_message_id=None
    elif failure=='wrong_remote':row.from_number='+15005550118'
    elif failure=='wrong_sender':row.to_number='+15005550119'
    elif failure=='wrong_account':row.provider_account_id='ACCforeign'
    await db.commit()
    with pytest.raises(HTTPException) as exc:await routes.resolve(db,tenant,t,c.phone)
    assert exc.value.detail['code']=='reply_route_unavailable'


@pytest.mark.asyncio
async def test_conflicting_timestamp_holds_but_same_route_tie_safe(setup):
    db,tenant,actor,c,t,b=setup
    tenant.sms_phone_number='+1500555'+str(uuid4().int%10000).zfill(4);await db.commit()
    now=datetime.now(timezone.utc)+timedelta(seconds=1)
    await add(db,tenant,c,t,b,when=now);await add(db,tenant,c,t,b,when=now)
    assert (await routes.resolve(db,tenant,t,c.phone)).provider=='callrail'
    await add(db,tenant,c,t,when=now)
    with pytest.raises(HTTPException) as exc:await routes.resolve(db,tenant,t,c.phone)
    assert exc.value.detail['code']=='reply_route_ambiguous'


@pytest.mark.asyncio
async def test_queued_route_changes_reject_without_provider_but_same_route_safe(setup,monkeypatch):
    db,tenant,actor,c,t,b=setup
    req=await request_for(db,tenant,t)
    op,_=await svc.create_operation(db,actor,tenant,t.id,req,uuid4().hex,TwilioMustNotSend())
    alternative=CallRailNumberBinding(tenant_id=tenant.id,account_id=b.account_id,company_id=b.company_id,
        tracker_id=b.tracker_id,sender_phone='+15005550112',enabled=True,credential_ref='CALLRAIL_TEST',signing_secret_ref='CALLRAIL_SIGNING')
    db.add(alternative);await db.flush()
    db.add(CallRailConversation(tenant_id=tenant.id,customer_id=c.id,thread_id=t.id,binding_id=alternative.id,customer_phone=c.phone,selected_for_sending=False));await db.commit()
    await add(db,tenant,c,t,alternative)
    async def forbidden(*a,**kw):pytest.fail('Changed route reached provider')
    monkeypatch.setattr(cr,'send',forbidden)
    await svc.dispatch_operation(db,op.id,TwilioMustNotSend());await db.refresh(op)
    assert op.state=='rejected' and op.attempt_count==0


@pytest.mark.asyncio
async def test_new_same_route_arrival_does_not_bind_to_evidence_id(setup,monkeypatch):
    db,tenant,actor,c,t,b=setup
    req=await request_for(db,tenant,t)
    op,_=await svc.create_operation(db,actor,tenant,t.id,req,uuid4().hex,TwilioMustNotSend())
    await add(db,tenant,c,t,b)
    calls=[]
    async def fake(*a,**kw):calls.append(a);return {'conversation_id':'synthetic-day'}
    monkeypatch.setattr(cr,'send',fake)
    await svc.dispatch_operation(db,op.id,TwilioMustNotSend());await db.refresh(op)
    assert op.state=='accepted' and len(calls)==1


@pytest.mark.asyncio
async def test_no_inbound_outbound_continuation_and_default_ignore_selection(setup):
    db,tenant,actor,c,t,b=setup
    tenant.sms_phone_number='+1500555'+str(uuid4().int%10000).zfill(4);tenant.sms_enabled=True
    rows=(await db.scalars(select(SMSMessage).where(SMSMessage.thread_id==t.id))).all()
    for row in rows:row.deleted_at=datetime.now(timezone.utc)
    await db.commit()
    assert (await routes.resolve(db,tenant,t,c.phone)).mode=='initiation'
    await add(db,tenant,c,t,b,inbound=False)
    assert (await routes.resolve(db,tenant,t,c.phone)).callrail.binding_id==b.id
    await add(db,tenant,c,t,inbound=False,delivery_status=Status.PENDING,twilio_message_sid=None)
    assert (await routes.resolve(db,tenant,t,c.phone)).provider=='callrail'


@pytest.mark.asyncio
async def test_sender_patch_rejected_without_metadata_mutation(setup):
    db,tenant,actor,c,t,b=setup
    assert await db.scalar(select(ConversationWorkflow).where(ConversationWorkflow.thread_id==t.id)) is None
    with pytest.raises(HTTPException) as exc:
        await patch_sender(t.id,SenderPatch(expected_version=999,binding_id=None),db=db,user=actor,sender=TwilioMustNotSend())
    assert exc.value.detail['code']=='sender_managed_automatically'
    assert await db.scalar(select(ConversationWorkflow).where(ConversationWorkflow.thread_id==t.id)) is None


@pytest.mark.asyncio
async def test_external_binding_disable_rechecked_before_provider(setup,monkeypatch):
    from app.db.session import AsyncSessionLocal
    db,tenant,actor,c,t,b=setup
    req=await request_for(db,tenant,t)
    op,_=await svc.create_operation(db,actor,tenant,t.id,req,uuid4().hex,TwilioMustNotSend())
    async with AsyncSessionLocal() as other:
        binding=await other.get(CallRailNumberBinding,b.id);binding.enabled=False;await other.commit()
    async def forbidden(*a,**kw):pytest.fail('Disabled route reached provider')
    monkeypatch.setattr(cr,'send',forbidden)
    await svc.dispatch_operation(db,op.id,TwilioMustNotSend());await db.refresh(op)
    assert op.state=='rejected' and op.attempt_count==0


@pytest.mark.asyncio
@pytest.mark.parametrize('older_proven',[False,True])
async def test_newest_sent_without_receipt_holds_instead_of_default_or_older_route(setup,older_proven):
    db,tenant,actor,c,t,b=setup
    tenant.sms_phone_number='+1500555'+str(uuid4().int%10000).zfill(4)
    tenant.sms_enabled=True
    inbound=(await db.scalars(select(SMSMessage).where(SMSMessage.thread_id==t.id))).all()
    for row in inbound:row.deleted_at=datetime.now(timezone.utc)
    await db.commit()
    if older_proven:
        await add(db,tenant,c,t,b,inbound=False,when=datetime.now(timezone.utc)-timedelta(minutes=1))
    await add(db,tenant,c,t,inbound=False,delivery_status=Status.SENT,twilio_message_sid=None)
    with pytest.raises(HTTPException) as exc:await routes.resolve(db,tenant,t,c.phone)
    assert exc.value.detail['code']=='reply_route_unavailable'
