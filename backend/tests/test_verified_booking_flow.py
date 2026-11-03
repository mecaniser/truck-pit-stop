from datetime import datetime,timedelta,timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4
import json
import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy import select,func
from app.db.models.tenant import Tenant
from app.db.models.customer import Customer
from app.db.models.service import Service
from app.db.models.appointment import Appointment,AppointmentStatus
from app.db.models.booking_payment import BookingPaymentAttempt,BookingReceipt
from app.db.models.user import User,UserRole
from app.db.models.invoice_settlement import TenantPaymentProviderConfiguration
from app.api.v1.endpoints.appointments import AppointmentCreate,BookingAttemptCreate,AppointmentUpdate,update_appointment,cancel_appointment
from app.api.v1.endpoints.visit_requests import VisitRequestCreate,create_visit_request,list_visit_requests
from app.services import booking_payments as booking
from app.services.booking_payment_provider import BookingProviderBinding,BookingProviderCapability,BookingProviderResult,BookingProviderError

@pytest_asyncio.fixture
async def setup_booking(db_session,monkeypatch):
    db_session.autoflush=False
    tenant=Tenant(name='Synthetic booking shop',slug=f'booking-{uuid4()}',timezone='America/New_York',labor_rate=Decimal('120'))
    db_session.add(tenant);await db_session.flush()
    customer=Customer(tenant_id=tenant.id,first_name='Synthetic',last_name='Booking',email=f'{uuid4()}@example.test')
    service=Service(tenant_id=tenant.id,name='Synthetic Oil Change',duration_minutes=60,base_price=Decimal('120'),requires_vehicle=False)
    db_session.add_all([customer,service]);await db_session.commit()
    user=User(id=uuid4(),email=f'{uuid4()}@example.test',first_name='Synthetic',last_name='Actor',tenant_id=tenant.id,customer_id=customer.id,role=UserRole.CUSTOMER)
    db_session.add(user);await db_session.flush()
    db_session.add(TenantPaymentProviderConfiguration(tenant_id=tenant.id,version=1,selected_provider='quickbooks_payments',readiness_state='ready',is_active=True,actor_user_id=user.id,actor_name_snapshot='Synthetic',provider_account_snapshot='realm-fixture',qbo_realm_snapshot='realm-fixture',writer_strategy='dieselbridge',idempotency_key=str(uuid4()),request_hash='a'*64))
    await db_session.commit()
    actor=SimpleNamespace(id=user.id,tenant_id=tenant.id,customer_id=customer.id,role=UserRole.CUSTOMER)
    binding=BookingProviderBinding('quickbooks_payments','realm-fixture',1,'sandbox',tenant.id)
    monkeypatch.setattr(booking.provider,'booking_provider_capability',AsyncMock(return_value=BookingProviderCapability(True,binding,'https://sandbox.example.test/tokens','Available',None)))
    body=AppointmentCreate(booking_kind='reserve',service_id=service.id,scheduled_at=datetime(2030,11,4,14,tzinfo=timezone.utc),customer_notes='Synthetic only')
    return tenant,customer,service,actor,body,binding

async def hold(db,setup,key='reserve-key-1'):
    return await booking.reserve(db,setup[3],setup[4],key)

def result(apt,attempt,*,state='succeeded',amount=12000,received=12000,environment='sandbox',provider_id='charge-fixture'):
    return BookingProviderResult(state,provider_id,provider_id,received if state=='succeeded' else 0,'usd',datetime.now(timezone.utc) if state=='succeeded' else None,None,'a'*64,booking.metadata(apt,attempt),environment,amount)

@pytest.mark.asyncio
async def test_hold_idempotency_expiry_and_no_provider_on_reads(db_session,setup_booking):
    apt=await hold(db_session,setup_booking);identity=apt.id
    replay=await hold(db_session,setup_booking)
    assert replay.id==identity and apt.status==AppointmentStatus.PENDING
    assert 890<(booking.utc(apt.hold_expires_at)-booking.now()).total_seconds()<=900
    with pytest.raises(HTTPException):await booking.reserve(db_session,setup_booking[3],setup_booking[4].model_copy(update={'customer_notes':'Changed'}),'reserve-key-1')
    await db_session.rollback();apt=await db_session.get(Appointment,identity)
    apt.hold_expires_at=booking.now()-timedelta(seconds=1);await db_session.commit()
    assert (await booking.snapshot(db_session,apt))['booking_payment_state']=='expired_unpaid'
    assert await booking.expire_holds(db_session)==1
    assert apt.booking_payment_state=='expired_unpaid'

@pytest.mark.asyncio
async def test_request_never_creates_appointment_or_payment(db_session,setup_booking,monkeypatch):
    service,actor=setup_booking[2:4]
    monkeypatch.setattr(booking.provider,'booking_provider_capability',AsyncMock(side_effect=AssertionError('Request never checks payments')))
    body=VisitRequestCreate(service_id=service.id,preferred_date=None,customer_notes='A preference only')
    first=await create_visit_request(body,db_session,actor,'visit-request-key')
    second=await create_visit_request(body,db_session,actor,'visit-request-key')
    assert first['id']==second['id'] and first['status']=='requested' and first['preferred_date'] is None
    assert not any(field in first for field in ['price','scheduled_at','paid_at','hold_expires_at'])
    assert await db_session.scalar(select(func.count(Appointment.id)))==0
    assert await db_session.scalar(select(func.count(BookingPaymentAttempt.id)))==0
    assert json.loads((await list_visit_requests(0,100,True,db_session,actor)).body)['total']==1

@pytest.mark.asyncio
async def test_verified_full_payment_is_only_confirmation_authority(db_session,setup_booking,monkeypatch):
    apt=await hold(db_session,setup_booking);actor=setup_booking[3]
    async def create(db,binding,**kwargs):
        attempt=await db.scalar(select(BookingPaymentAttempt).where(BookingPaymentAttempt.appointment_id==apt.id))
        assert attempt.state=='creating' and kwargs['amount_minor']==12000
        return result(apt,attempt)
    creator=AsyncMock(side_effect=create);monkeypatch.setattr(booking.provider,'create_booking_payment',creator)
    body=BookingAttemptCreate(expected_version=apt.booking_version,price_snapshot_sha256=apt.price_snapshot_sha256,quickbooks_token='opaque-fixture')
    response=await booking.start_attempt(db_session,actor,apt.id,body,'payment-request-key')
    assert response['booking_status']=='confirmed' and response['receipt']['amount']=='120'
    assert apt.status==AppointmentStatus.CONFIRMED and apt.paid_at
    assert await db_session.scalar(select(func.count(BookingReceipt.id)))==1
    attempt=await db_session.scalar(select(BookingPaymentAttempt))
    assert 'opaque-fixture' not in repr(attempt.__dict__)
    monkeypatch.setattr(booking.provider,'retrieve_booking_payment',AsyncMock(return_value=result(apt,attempt)))
    replay=await booking.start_attempt(db_session,actor,apt.id,body,'payment-request-key')
    assert replay['receipt']['id']==response['receipt']['id']
    creator.assert_awaited_once()
    assert await db_session.scalar(select(func.count(BookingReceipt.id)))==1

@pytest.mark.asyncio
async def test_unknown_keeps_known_provider_binding_and_blocks_another_charge(db_session,setup_booking,monkeypatch):
    apt=await hold(db_session,setup_booking);actor=setup_booking[3]
    creator=AsyncMock(side_effect=BookingProviderError('Pending',outcome_unknown=True,provider_id='charge-accepted'))
    monkeypatch.setattr(booking.provider,'create_booking_payment',creator)
    body=BookingAttemptCreate(expected_version=1,price_snapshot_sha256=apt.price_snapshot_sha256,quickbooks_token='token-fixture')
    response=await booking.start_attempt(db_session,actor,apt.id,body,'payment-unknown-key')
    assert response['state']=='outcome_unknown' and response['booking_payment_state']=='payment_processing'
    attempt=await db_session.scalar(select(BookingPaymentAttempt));assert attempt.provider_intent_id=='charge-accepted'
    apt.hold_expires_at=booking.now()-timedelta(seconds=1);await db_session.commit()
    monkeypatch.setattr(booking.provider,'cancel_unpaid_booking_payment',AsyncMock(side_effect=BookingProviderError('Unknown',outcome_unknown=True)))
    await booking.expire_holds(db_session)
    assert (await booking.snapshot(db_session,apt))['booking_payment_state']=='payment_processing'
    with pytest.raises(HTTPException):await booking.start_attempt(db_session,actor,apt.id,body.model_copy(update={'expected_version':apt.booking_version}),'another-payment-key')
    creator.assert_awaited_once()

@pytest.mark.asyncio
async def test_bad_evidence_never_confirms_and_late_success_needs_review(db_session,setup_booking,monkeypatch):
    apt=await hold(db_session,setup_booking);identity=apt.id;actor=setup_booking[3]
    monkeypatch.setattr(booking.provider,'create_booking_payment',AsyncMock(side_effect=BookingProviderError('Unknown',outcome_unknown=True,provider_id='charge-fixture')))
    await booking.start_attempt(db_session,actor,identity,BookingAttemptCreate(expected_version=1,price_snapshot_sha256=apt.price_snapshot_sha256,quickbooks_token='token'),'payment-evidence-key')
    attempt=await db_session.scalar(select(BookingPaymentAttempt));attempt_id=attempt.id
    for evidence in [result(apt,attempt,amount=11999),result(apt,attempt,environment='production')]:
        with pytest.raises(HTTPException):await booking.apply_result(db_session,identity,attempt_id,evidence)
        await db_session.rollback();apt=await db_session.get(Appointment,identity);attempt=await db_session.get(BookingPaymentAttempt,attempt_id)
    apt.hold_expires_at=booking.now()-timedelta(seconds=1);await db_session.commit()
    await booking.apply_result(db_session,identity,attempt_id,result(apt,attempt))
    assert apt.booking_payment_state=='payment_received_review' and apt.status==AppointmentStatus.PENDING
    assert await db_session.scalar(select(func.count(BookingReceipt.id)))==1

@pytest.mark.asyncio
async def test_staff_cannot_bypass_receipt_or_release_unknown(db_session,setup_booking,monkeypatch):
    apt=await hold(db_session,setup_booking);identity=apt.id;actor=setup_booking[3]
    staff=SimpleNamespace(tenant_id=actor.tenant_id,customer_id=None,role=UserRole.GARAGE_OWNER)
    with pytest.raises(HTTPException):await update_appointment(identity,AppointmentUpdate(status=AppointmentStatus.CONFIRMED),db_session,staff)
    await db_session.rollback();apt=await db_session.get(Appointment,identity)
    monkeypatch.setattr(booking.provider,'create_booking_payment',AsyncMock(side_effect=BookingProviderError('Unknown',outcome_unknown=True)))
    await booking.start_attempt(db_session,actor,identity,BookingAttemptCreate(expected_version=1,price_snapshot_sha256=apt.price_snapshot_sha256,quickbooks_token='token'),'payment-cancel-key')
    with pytest.raises(HTTPException):await cancel_appointment(identity,db_session,actor)
    assert apt.status==AppointmentStatus.PENDING

@pytest.mark.asyncio
async def test_changed_provider_configuration_never_silently_switches_checkout(db_session,setup_booking,monkeypatch):
    apt=await hold(db_session,setup_booking)
    from dataclasses import replace
    changed=replace(setup_booking[5],provider='stripe_connect',account_id='acct_fixture',configuration_version=2)
    monkeypatch.setattr(booking.provider,'booking_provider_capability',AsyncMock(return_value=BookingProviderCapability(True,changed)))
    creator=AsyncMock(side_effect=AssertionError('Provider must not be invoked'))
    monkeypatch.setattr(booking.provider,'create_booking_payment',creator)
    with pytest.raises(HTTPException) as error:
        await booking.start_attempt(db_session,setup_booking[3],apt.id,BookingAttemptCreate(expected_version=1,price_snapshot_sha256=apt.price_snapshot_sha256,quickbooks_token='opaque'),'provider-switch-key')
    assert error.value.detail['code']=='booking_provider_changed'
    creator.assert_not_awaited()
    assert await db_session.scalar(select(func.count(BookingPaymentAttempt.id)))==0

@pytest.mark.asyncio
@pytest.mark.parametrize('change',['amount','currency','metadata','environment','received','charge'])
async def test_untrusted_provider_evidence_never_creates_receipt(db_session,setup_booking,monkeypatch,change):
    from dataclasses import replace
    apt=await hold(db_session,setup_booking);actor=setup_booking[3]
    monkeypatch.setattr(booking.provider,'create_booking_payment',AsyncMock(side_effect=BookingProviderError('Unknown',outcome_unknown=True,provider_id='charge-fixture')))
    await booking.start_attempt(db_session,actor,apt.id,BookingAttemptCreate(expected_version=1,price_snapshot_sha256=apt.price_snapshot_sha256,quickbooks_token='opaque'),'bad-proof-payment')
    attempt=await db_session.scalar(select(BookingPaymentAttempt));evidence=result(apt,attempt)
    fields={'amount':{'amount_minor':11999},'currency':{'currency':'eur'},'metadata':{'metadata':{**evidence.metadata,'customer_id':str(uuid4())}},'environment':{'environment':'production'},'received':{'amount_received_minor':11999},'charge':{'charge_id':None}}
    with pytest.raises(HTTPException):await booking.apply_result(db_session,apt.id,attempt.id,replace(evidence,**fields[change]))
    assert apt.status==AppointmentStatus.PENDING
    assert await db_session.scalar(select(func.count(BookingReceipt.id)))==0

@pytest.mark.asyncio
async def test_expired_hold_cannot_create_attempt_and_request_does_not_block_slot(db_session,setup_booking,monkeypatch):
    apt=await hold(db_session,setup_booking);actor=setup_booking[3]
    monkeypatch.setattr(booking,'now',lambda:booking.utc(apt.hold_expires_at)+timedelta(seconds=1))
    creator=AsyncMock(side_effect=AssertionError('Expired hold cannot charge'))
    monkeypatch.setattr(booking.provider,'create_booking_payment',creator)
    with pytest.raises(HTTPException):await booking.start_attempt(db_session,actor,apt.id,BookingAttemptCreate(expected_version=1,price_snapshot_sha256=apt.price_snapshot_sha256,quickbooks_token='opaque'),'expired-payment-key')
    creator.assert_not_awaited()
    assert not await booking.blocking(db_session,apt.tenant_id,booking.utc(apt.scheduled_at),booking.utc(apt.scheduled_at)+timedelta(minutes=60))

@pytest.mark.asyncio
async def test_price_change_does_not_reprice_existing_reservation(db_session,setup_booking,monkeypatch):
    apt=await hold(db_session,setup_booking)
    setup_booking[2].base_price=Decimal('999');await db_session.commit()
    async def create(db,binding,**kwargs):
        assert kwargs['amount_minor']==12000
        attempt=await db.scalar(select(BookingPaymentAttempt));return result(apt,attempt)
    monkeypatch.setattr(booking.provider,'create_booking_payment',AsyncMock(side_effect=create))
    response=await booking.start_attempt(db_session,setup_booking[3],apt.id,BookingAttemptCreate(expected_version=1,price_snapshot_sha256=apt.price_snapshot_sha256,quickbooks_token='opaque'),'price-snapshot-key')
    assert response['amount']=='120' and response['booking_status']=='confirmed'

@pytest.mark.asyncio
async def test_foreign_customer_and_tenant_cannot_read_or_verify_reservation(db_session,setup_booking):
    apt=await hold(db_session,setup_booking);actor=setup_booking[3]
    from copy import copy
    for attribute in ['tenant_id','customer_id']:
        foreign=copy(actor);setattr(foreign,attribute,uuid4())
        with pytest.raises(HTTPException) as error:await booking.admitted_appointment(db_session,foreign,apt.id)
        assert error.value.status_code==404

@pytest.mark.asyncio
async def test_missing_reserve_kind_is_not_legacy_creation_bypass(db_session,setup_booking):
    with pytest.raises(HTTPException) as error:await booking.reserve(db_session,setup_booking[3],setup_booking[4].model_copy(update={'booking_kind':None}),'missing-kind-key')
    assert error.value.status_code==422
    assert await db_session.scalar(select(func.count(Appointment.id)))==0

@pytest.mark.asyncio
async def test_signed_webhook_recovers_timed_out_create_only_through_exact_server_retrieval(db_session,setup_booking,monkeypatch):
    from dataclasses import replace
    chosen=replace(setup_booking[5],provider='stripe_connect',account_id='acct_fixture')
    monkeypatch.setattr(booking.provider,'booking_provider_capability',AsyncMock(return_value=BookingProviderCapability(True,chosen)))
    apt=await hold(db_session,setup_booking)
    monkeypatch.setattr(booking.provider,'create_booking_payment',AsyncMock(side_effect=BookingProviderError('Unknown',outcome_unknown=True)))
    await booking.start_attempt(db_session,setup_booking[3],apt.id,BookingAttemptCreate(expected_version=1,price_snapshot_sha256=apt.price_snapshot_sha256),'webhook-timeout-key')
    attempt=await db_session.scalar(select(BookingPaymentAttempt));assert attempt.provider_intent_id is None
    evidence=result(apt,attempt,provider_id='pi_recovered')
    retriever=AsyncMock(return_value=evidence);monkeypatch.setattr(booking.provider,'recover_created_booking_payment',retriever)
    obj={'id':'pi_recovered','metadata':booking.metadata(apt,attempt),'status':'succeeded','amount':12000,'amount_received':12000,'currency':'usd','livemode':False,'latest_charge':'pi_recovered'}
    event={'id':'evt_recovered','type':'payment_intent.succeeded','account':'acct_fixture','livemode':False,'data':{'object':obj}}
    assert await booking.dispatch_connect_event(db_session,event)
    retriever.assert_awaited_once()
    assert attempt.provider_intent_id=='pi_recovered' and apt.status==AppointmentStatus.CONFIRMED
    assert await db_session.scalar(select(func.count(BookingReceipt.id)))==1
    monkeypatch.setattr(booking.provider,'retrieve_booking_payment',AsyncMock(return_value=evidence))
    assert await booking.dispatch_connect_event(db_session,event)
    assert await db_session.scalar(select(func.count(BookingReceipt.id)))==1

@pytest.mark.asyncio
async def test_signed_refund_replays_preserve_gross_and_never_restore_full_payment(db_session,setup_booking,monkeypatch):
    from dataclasses import replace
    chosen=replace(setup_booking[5],provider='stripe_connect',account_id='acct_refund_fixture')
    monkeypatch.setattr(booking.provider,'booking_provider_capability',AsyncMock(return_value=BookingProviderCapability(True,chosen)))
    apt=await hold(db_session,setup_booking)
    async def create(db,binding,**kwargs):
        attempt=await db.scalar(select(BookingPaymentAttempt));return result(apt,attempt,provider_id='pi_refund_fixture')
    creator=AsyncMock(side_effect=create);monkeypatch.setattr(booking.provider,'create_booking_payment',creator)
    await booking.start_attempt(db_session,setup_booking[3],apt.id,BookingAttemptCreate(expected_version=1,price_snapshot_sha256=apt.price_snapshot_sha256),'refund-proof-payment')
    event={'id':'evt_partial','type':'charge.refunded','account':chosen.account_id,'livemode':False,'data':{'object':{'id':'pi_refund_fixture','payment_intent':'pi_refund_fixture','amount':12000,'amount_refunded':5000,'currency':'usd'}}}
    await booking.dispatch_connect_event(db_session,event)
    receipt=await db_session.scalar(select(BookingReceipt));assert receipt.amount_received_minor==12000 and receipt.refunded_amount_minor==5000
    assert apt.booking_payment_state=='refund_pending' and apt.status==AppointmentStatus.PENDING
    await booking.dispatch_connect_event(db_session,event)
    event={**event,'id':'evt_old_partial','data':{'object':{**event['data']['object'],'amount_refunded':3000}}}
    await booking.dispatch_connect_event(db_session,event)
    assert receipt.refunded_amount_minor==5000
    event={**event,'id':'evt_full','data':{'object':{**event['data']['object'],'amount_refunded':12000}}}
    await booking.dispatch_connect_event(db_session,event)
    assert receipt.refunded_amount_minor==12000 and apt.booking_payment_state=='refunded'
    attempt=await db_session.scalar(select(BookingPaymentAttempt))
    await booking.apply_result(db_session,apt.id,attempt.id,result(apt,attempt,provider_id='pi_refund_fixture'))
    assert apt.booking_payment_state=='refunded'
    assert await db_session.scalar(select(func.count(BookingReceipt.id)))==1
    creator.assert_awaited_once()

@pytest.mark.asyncio
@pytest.mark.parametrize('wrong',['account','metadata'])
async def test_unknown_create_webhook_rejects_foreign_binding_before_any_retrieval(db_session,setup_booking,monkeypatch,wrong):
    from dataclasses import replace
    chosen=replace(setup_booking[5],provider='stripe_connect',account_id='acct_webhook_fixture')
    monkeypatch.setattr(booking.provider,'booking_provider_capability',AsyncMock(return_value=BookingProviderCapability(True,chosen)))
    apt=await hold(db_session,setup_booking)
    monkeypatch.setattr(booking.provider,'create_booking_payment',AsyncMock(side_effect=BookingProviderError('Unknown',outcome_unknown=True)))
    await booking.start_attempt(db_session,setup_booking[3],apt.id,BookingAttemptCreate(expected_version=1,price_snapshot_sha256=apt.price_snapshot_sha256),'unknown-webhook-payment')
    attempt=await db_session.scalar(select(BookingPaymentAttempt));fields=booking.metadata(apt,attempt)
    if wrong=='metadata':fields={**fields,'customer_id':str(uuid4())}
    event={'id':'evt_wrong_binding','type':'payment_intent.succeeded','account':'acct_foreign' if wrong=='account' else chosen.account_id,'livemode':False,'data':{'object':{'id':'pi_unadopted','metadata':fields}}}
    retrieval=AsyncMock(side_effect=AssertionError('Wrong binding must not retrieve'));monkeypatch.setattr(booking.provider,'retrieve_booking_payment',retrieval)
    with pytest.raises(HTTPException):await booking.dispatch_connect_event(db_session,event)
    retrieval.assert_not_awaited()
    assert attempt.provider_intent_id is None and apt.status==AppointmentStatus.PENDING
    assert await db_session.scalar(select(func.count(BookingReceipt.id)))==0

@pytest.mark.asyncio
async def test_paid_cancelled_reservation_cannot_be_reconfirmed_or_unconfirmed_via_put(db_session,setup_booking,monkeypatch):
    apt=await hold(db_session,setup_booking);identity=apt.id;actor=setup_booking[3]
    async def create(db,binding,**kwargs):return result(apt,await db.scalar(select(BookingPaymentAttempt)))
    monkeypatch.setattr(booking.provider,'create_booking_payment',AsyncMock(side_effect=create))
    await booking.start_attempt(db_session,actor,identity,BookingAttemptCreate(expected_version=1,price_snapshot_sha256=apt.price_snapshot_sha256,quickbooks_token='fixture'),'paid-status-guard-key')
    staff=SimpleNamespace(tenant_id=actor.tenant_id,customer_id=None,role=UserRole.GARAGE_OWNER)
    with pytest.raises(HTTPException):await update_appointment(identity,AppointmentUpdate(status=AppointmentStatus.PENDING),db_session,staff)
    await db_session.rollback();apt=await db_session.get(Appointment,identity)
    await cancel_appointment(identity,db_session,actor)
    assert apt.status==AppointmentStatus.CANCELLED
    replacement=await booking.reserve(db_session,actor,setup_booking[4],'replacement-held-slot')
    with pytest.raises(HTTPException):await update_appointment(identity,AppointmentUpdate(status=AppointmentStatus.CONFIRMED),db_session,staff)
    await db_session.rollback();apt=await db_session.get(Appointment,identity)
    assert apt.status==AppointmentStatus.CANCELLED and apt.confirmed_receipt_id is not None
    assert await db_session.scalar(select(func.count(BookingReceipt.id)))==1

@pytest.mark.asyncio
async def test_worker_verifies_known_processing_identity_before_expiry_without_another_charge(db_session,setup_booking,monkeypatch):
    apt=await hold(db_session,setup_booking)
    creator=AsyncMock(side_effect=BookingProviderError('Pending',outcome_unknown=True,provider_id='known-pending-charge'))
    monkeypatch.setattr(booking.provider,'create_booking_payment',creator)
    await booking.start_attempt(db_session,setup_booking[3],apt.id,BookingAttemptCreate(expected_version=1,price_snapshot_sha256=apt.price_snapshot_sha256,quickbooks_token='fixture'),'worker-reconcile-key')
    attempt=await db_session.scalar(select(BookingPaymentAttempt))
    view=await booking.snapshot(db_session,apt)
    assert view['payment_attempt_id']==str(attempt.id) and view['payment_attempt_state']=='outcome_unknown'
    retrieval=AsyncMock(return_value=result(apt,attempt,provider_id='known-pending-charge'))
    monkeypatch.setattr(booking.provider,'retrieve_booking_payment',retrieval)
    assert await booking.reconcile_live_attempts(db_session)==1
    assert apt.status==AppointmentStatus.CONFIRMED and apt.booking_payment_state=='paid'
    creator.assert_awaited_once();retrieval.assert_awaited_once()
    assert await db_session.scalar(select(func.count(BookingReceipt.id)))==1

@pytest.mark.asyncio
@pytest.mark.parametrize('timely',[True,False])
async def test_provider_paid_time_not_browser_observation_controls_timely_confirmation(db_session,setup_booking,monkeypatch,timely):
    from dataclasses import replace
    apt=await hold(db_session,setup_booking)
    monkeypatch.setattr(booking.provider,'create_booking_payment',AsyncMock(side_effect=BookingProviderError('Pending',outcome_unknown=True,provider_id='timing-charge')))
    await booking.start_attempt(db_session,setup_booking[3],apt.id,BookingAttemptCreate(expected_version=1,price_snapshot_sha256=apt.price_snapshot_sha256,quickbooks_token='fixture'),'provider-time-window-key')
    attempt=await db_session.scalar(select(BookingPaymentAttempt));expiry=booking.utc(apt.hold_expires_at)
    actual_paid=expiry-timedelta(minutes=1) if timely else expiry+timedelta(seconds=1)
    monkeypatch.setattr(booking,'now',lambda:expiry+timedelta(minutes=2))
    await booking.apply_result(db_session,apt.id,attempt.id,replace(result(apt,attempt,provider_id='timing-charge'),paid_at=actual_paid))
    assert apt.status==(AppointmentStatus.CONFIRMED if timely else AppointmentStatus.PENDING)
    assert apt.booking_payment_state==('paid' if timely else 'payment_received_review')
    receipt=await db_session.scalar(select(BookingReceipt));assert booking.utc(receipt.received_at)==actual_paid

@pytest.mark.asyncio
async def test_timely_money_cannot_reclaim_cleanly_expired_reallocated_slot(db_session,setup_booking,monkeypatch):
    from dataclasses import replace
    apt=await hold(db_session,setup_booking);actor=setup_booking[3]
    monkeypatch.setattr(booking.provider,'create_booking_payment',AsyncMock(side_effect=BookingProviderError('Pending',outcome_unknown=True,provider_id='released-charge')))
    await booking.start_attempt(db_session,actor,apt.id,BookingAttemptCreate(expected_version=1,price_snapshot_sha256=apt.price_snapshot_sha256,quickbooks_token='fixture'),'released-money-key')
    attempt=await db_session.scalar(select(BookingPaymentAttempt));expiry=booking.utc(apt.hold_expires_at)
    monkeypatch.setattr(booking,'now',lambda:expiry+timedelta(minutes=1))
    cancelled=replace(result(apt,attempt,provider_id='released-charge'),state='cancelled',amount_received_minor=0,paid_at=None)
    await booking.apply_result(db_session,apt.id,attempt.id,cancelled)
    assert apt.booking_payment_state=='expired_unpaid'
    other=await booking.reserve(db_session,actor,setup_booking[4],'reallocated-slot-hold')
    await booking.apply_result(db_session,apt.id,attempt.id,replace(result(apt,attempt,provider_id='released-charge'),paid_at=expiry-timedelta(minutes=1)))
    assert apt.status==AppointmentStatus.PENDING and apt.booking_payment_state=='payment_received_review'
    assert other.booking_payment_state=='unpaid_hold'

@pytest.mark.asyncio
async def test_staff_read_fields_are_private_and_incoming_requests_are_visible_only_in_tenant(db_session,setup_booking):
    apt=await hold(db_session,setup_booking);actor=setup_booking[3]
    customer_view=await booking.snapshot(db_session,apt,actor=actor)
    assert all(field not in customer_view for field in ['repair_order_id','application_review_required','accounting_classification'])
    staff=SimpleNamespace(role=UserRole.RECEPTIONIST,tenant_id=actor.tenant_id,customer_id=None)
    staff_view=await booking.snapshot(db_session,apt,actor=staff)
    assert 'repair_order_id' in staff_view and 'application_review_required' in staff_view
    await create_visit_request(VisitRequestCreate(service_id=setup_booking[2].id),db_session,actor,'staff-visible-request')
    assert json.loads((await list_visit_requests(0,100,True,db_session,staff)).body)['total']==1
    foreign=SimpleNamespace(role=UserRole.GARAGE_OWNER,tenant_id=uuid4(),customer_id=None)
    assert json.loads((await list_visit_requests(0,100,True,db_session,foreign)).body)['total']==0
    with pytest.raises(HTTPException):await list_visit_requests(0,100,True,db_session,foreign,actor.customer_id)

@pytest.mark.asyncio
@pytest.mark.parametrize('field,value',[('customer_id',None),('amount_minor',11999),('configuration_version',2),('environment','production'),('currency','eur')])
async def test_attempt_crossrow_binding_mismatch_cannot_create_receipt(db_session,setup_booking,monkeypatch,field,value):
    apt=await hold(db_session,setup_booking)
    monkeypatch.setattr(booking.provider,'create_booking_payment',AsyncMock(side_effect=BookingProviderError('Pending',outcome_unknown=True,provider_id='binding-charge')))
    await booking.start_attempt(db_session,setup_booking[3],apt.id,BookingAttemptCreate(expected_version=1,price_snapshot_sha256=apt.price_snapshot_sha256,quickbooks_token='fixture'),'crossrow-binding-key')
    attempt=await db_session.scalar(select(BookingPaymentAttempt))
    # In-memory fault injection exercises the application cross-row guard;
    # immutable PostgreSQL provider bindings prevent such updates in deployed DB.
    fault=SimpleNamespace(**{name:getattr(attempt,name) for name in ['appointment_id','tenant_id','customer_id','amount_minor','configuration_version','environment','currency']})
    setattr(fault,field,value)
    with pytest.raises(HTTPException) as error:booking.validate_attempt_binding(apt,fault)
    assert error.value.detail['code']=='booking_attempt_binding_mismatch'
    assert apt.status==AppointmentStatus.PENDING
