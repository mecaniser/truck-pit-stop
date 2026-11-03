"""Verified prepaid reservations. No invoice, repair-sale, notification or revenue writer."""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from hashlib import sha256
import json
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import select, text, or_
from sqlalchemy.orm import selectinload
from app.db.models.appointment import Appointment, AppointmentStatus
from app.db.models.booking_payment import BookingPaymentAttempt, BookingReceipt, BookingPaymentEvent
from app.db.models.customer import Customer
from app.db.models.service import Service, ServicePart
from app.db.models.tenant import Tenant
from app.db.models.vehicle import Vehicle
from app.db.models.user import UserRole
from app.services.financial_transaction_lock import lock_tenant_financials
from app.services import booking_payment_provider as provider

LIVE = {'created','creating','requires_action','requires_payment_method','processing','outcome_unknown'}
STAFF = {UserRole.GARAGE_OWNER, UserRole.GARAGE_ADMIN, UserRole.RECEPTIONIST}

def utc(value):
    return value.replace(tzinfo=value.tzinfo or timezone.utc).astimezone(timezone.utc)

def now():
    return datetime.now(timezone.utc)

def digest(value):
    return sha256(json.dumps(value,sort_keys=True,separators=(',',':'),default=str).encode()).hexdigest()

def fail(code, message, status=409):
    raise HTTPException(status_code=status,detail={'code':code,'message':message})

def key(value):
    if not isinstance(value,str) or not 8 <= len(value.strip()) <= 200:
        fail('idempotency_key_required','A valid Idempotency-Key is required.',422)
    return value.strip()

async def locks(db,tenant_id):
    from app.services.invoice_settlement_service import SettlementDomainError
    try:await lock_tenant_financials(db,tenant_id)
    except SettlementDomainError:fail('booking_busy','Another reservation update is in progress. Refresh and retry.')
    if db.get_bind().dialect.name=='postgresql':
        number=int.from_bytes(sha256(f'booking-schedule:{tenant_id}'.encode()).digest()[:8],'big',signed=True)
        await db.execute(text('SELECT pg_advisory_xact_lock(:key)'),{'key':number})

async def principal(db,actor,service_id,vehicle_id):
    if actor.role!=UserRole.CUSTOMER or not actor.tenant_id or not actor.customer_id:
        raise HTTPException(404,'Service not found')
    tenant=await db.scalar(select(Tenant).where(Tenant.id==actor.tenant_id,Tenant.is_active.is_(True),Tenant.deleted_at.is_(None)))
    customer=await db.scalar(select(Customer.id).where(Customer.id==actor.customer_id,Customer.tenant_id==actor.tenant_id,Customer.deleted_at.is_(None)))
    service=await db.scalar(select(Service).where(Service.id==service_id,Service.tenant_id==actor.tenant_id,Service.is_active.is_(True),Service.deleted_at.is_(None)).options(selectinload(Service.service_parts).selectinload(ServicePart.inventory_item)))
    if not tenant or not customer or not service: raise HTTPException(404,'Service not found')
    if service.requires_vehicle and not vehicle_id: fail('vehicle_required','Choose your vehicle.',422)
    if vehicle_id:
        vehicle=await db.scalar(select(Vehicle.id).where(Vehicle.id==vehicle_id,Vehicle.tenant_id==actor.tenant_id,Vehicle.customer_id==actor.customer_id,Vehicle.deleted_at.is_(None)))
        if not vehicle: raise HTTPException(404,'Vehicle not found')
    return tenant,service

async def admitted_appointment(db,actor,appointment_id,*,write=False):
    if not actor.tenant_id or actor.role not in {UserRole.CUSTOMER,*STAFF}: raise HTTPException(404,'Appointment not found')
    filters=[Appointment.id==appointment_id,Appointment.tenant_id==actor.tenant_id,Appointment.deleted_at.is_(None)]
    if actor.role==UserRole.CUSTOMER:
        if not actor.customer_id: raise HTTPException(404,'Appointment not found')
        filters.append(Appointment.customer_id==actor.customer_id)
    query=select(Appointment).where(*filters).execution_options(populate_existing=True,autoflush=False)
    if write: query=query.with_for_update()
    apt=await db.scalar(query)
    if apt is None: raise HTTPException(404,'Appointment not found')
    return apt

async def blocking(db,tenant_id,start,end,*,exclude=None,at=None):
    at=at or now()
    rows=(await db.scalars(select(Appointment).where(Appointment.tenant_id==tenant_id,Appointment.deleted_at.is_(None),Appointment.scheduled_at<end,or_(Appointment.status.in_([AppointmentStatus.CONFIRMED,AppointmentStatus.IN_PROGRESS]),(Appointment.booking_payment_version==1)&(Appointment.status==AppointmentStatus.PENDING))))).all()
    for apt in rows:
        if apt.id==exclude: continue
        holds=apt.status in {AppointmentStatus.CONFIRMED,AppointmentStatus.IN_PROGRESS}
        if not holds and apt.booking_payment_version==1:
            holds=(apt.booking_payment_state=='payment_processing' or (apt.booking_payment_state=='unpaid_hold' and apt.hold_expires_at and utc(apt.hold_expires_at)>at))
        if holds and start<utc(apt.scheduled_at)+timedelta(minutes=apt.duration_minutes) and end>utc(apt.scheduled_at): return True
    return False

async def price(service,tenant):
    if service.duration_minutes<=0: fail('booking_service_unavailable','This service is unavailable for online reservations.')
    if service.base_price is not None: amount=Decimal(str(service.base_price))
    else:
        if tenant.labor_rate is None:fail('booking_price_unavailable','The shop labor rate is unavailable.')
        rate=Decimal(str(tenant.labor_rate))
        if not rate.is_finite() or rate<=0:fail('booking_price_unavailable','The shop labor rate is unavailable.')
        amount=(rate*Decimal(service.duration_minutes)/60).quantize(Decimal('.01'))
        for part in service.service_parts:
            item=part.inventory_item
            if part.tenant_id!=tenant.id or part.service_id!=service.id or not item or item.tenant_id!=tenant.id or item.deleted_at is not None:
                fail('booking_price_unavailable','Service parts must be reviewed before reserving.')
            quantity=Decimal(str(part.quantity));unit_price=Decimal(str(item.selling_price))
            if not quantity.is_finite() or quantity<=0 or not unit_price.is_finite() or unit_price<0:fail('booking_price_unavailable','Service parts must be reviewed before reserving.')
            amount+=unit_price*quantity
        amount=amount.quantize(Decimal('.01'))
    if not amount.is_finite() or amount<Decimal('.50') or amount*100!=(amount*100).to_integral_value(): fail('booking_price_unavailable','This service price is unavailable for online reservations.')
    return amount

async def reserve(db,actor,body,request_key):
    request_key=key(request_key)
    if body.booking_kind!='reserve': fail('booking_kind_required','Choose Reserve a time or Request a visit.',422)
    if not body.scheduled_at.tzinfo: fail('booking_timezone_required','Choose a shop time.',422)
    scheduled=utc(body.scheduled_at)
    request_hash=digest({'service_id':body.service_id,'vehicle_id':body.vehicle_id,'scheduled_at':scheduled.isoformat(),'customer_notes':body.customer_notes,'booking_kind':'reserve','customer_id':actor.customer_id})
    if not actor.tenant_id: raise HTTPException(404,'Service not found')
    await locks(db,actor.tenant_id)
    existing=await db.scalar(select(Appointment).where(Appointment.tenant_id==actor.tenant_id,Appointment.booking_idempotency_key==request_key))
    if existing:
        if existing.customer_id!=actor.customer_id or existing.booking_request_sha256!=request_hash: fail('idempotency_key_reused','This request key was already used for a different reservation.')
        return existing
    tenant,service=await principal(db,actor,body.service_id,body.vehicle_id)
    capability=await provider.booking_provider_capability(db,tenant)
    if not capability.available: fail(capability.reason_code or 'booking_payment_unavailable',capability.message)
    try: local=scheduled.astimezone(ZoneInfo(tenant.timezone))
    except Exception: fail('booking_timezone_unavailable','The shop timezone is unavailable.')
    if scheduled<=now() or not 8<=local.hour<17 or local.minute not in (0,30) or local.second or local.microsecond: fail('booking_slot_unavailable','Choose an available shop time.')
    amount=await price(service,tenant)
    if await blocking(db,tenant.id,scheduled,scheduled+timedelta(minutes=service.duration_minutes)): fail('booking_slot_unavailable','This time is no longer available.')
    apt=Appointment(id=uuid4(),tenant_id=tenant.id,customer_id=actor.customer_id,vehicle_id=body.vehicle_id,service_id=service.id,scheduled_at=scheduled,duration_minutes=service.duration_minutes,status=AppointmentStatus.PENDING,price=amount,customer_notes=body.customer_notes,confirmation_number=f'APT-{uuid4().hex[:12].upper()}',booking_kind='reserve',booking_payment_version=1,booking_payment_state='unpaid_hold',booking_version=1,hold_expires_at=now()+timedelta(minutes=15),booking_currency='usd',booking_idempotency_key=request_key,booking_request_sha256=request_hash,booking_provider_configuration_version=capability.binding.configuration_version,booking_provider_environment=capability.binding.environment)
    apt.price_snapshot_sha256=digest({'tenant_id':tenant.id,'customer_id':actor.customer_id,'service_id':service.id,'vehicle_id':body.vehicle_id,'scheduled_at':scheduled.isoformat(),'duration_minutes':service.duration_minutes,'price':str(amount),'currency':'usd','notes':body.customer_notes,'provider_configuration_version':capability.binding.configuration_version,'provider_environment':capability.binding.environment})
    db.add(apt)
    await db.flush()
    db.add(BookingPaymentEvent(tenant_id=apt.tenant_id,appointment_id=apt.id,source='reservation',after_state='unpaid_hold',event_at=now()))
    await db.commit()
    return apt

async def receipt_summary(db,apt):
    receipt=await db.scalar(select(BookingReceipt).where(BookingReceipt.tenant_id==apt.tenant_id,BookingReceipt.appointment_id==apt.id))
    if not receipt:return None
    from app.services.booking_application_accounting import receipt_balances
    from app.services.invoice_settlement_service import SettlementDomainError
    try:
        balances=await receipt_balances(db,apt.tenant_id,receipt.id)
        unapplied=str(Decimal(balances['unapplied_minor'])/100)
        applied=str(Decimal(balances['applied_minor'])/100)
        review=False
    except SettlementDomainError:
        unapplied=None;applied=None;review=True
    return {'applied_amount':applied,'payment_verification_required':review,'id':str(receipt.id),'gross_amount':str(Decimal(receipt.amount_received_minor)/100),'net_amount':str(Decimal(receipt.amount_received_minor-receipt.refunded_amount_minor)/100),'unapplied_amount':unapplied,'outstanding_amount':unapplied,'reservation_balance':str(max(Decimal('0'),Decimal(apt.price)-Decimal(receipt.amount_received_minor-receipt.refunded_amount_minor)/100)),'amount':str(Decimal(receipt.amount_received_minor)/100),'currency':receipt.currency,'received_at':receipt.received_at,'refunded_amount':str(Decimal(receipt.refunded_amount_minor)/100),'verification_basis':receipt.verification_basis}

async def snapshot(db,apt,service_name=None,*,actor=None):
    state=apt.booking_payment_state
    latest_attempt=None
    if apt.booking_payment_version==1:
        latest_attempt=await db.scalar(select(BookingPaymentAttempt).where(BookingPaymentAttempt.tenant_id==apt.tenant_id,BookingPaymentAttempt.appointment_id==apt.id).order_by(BookingPaymentAttempt.created_at.desc()).limit(1))
        live=await db.scalar(select(BookingPaymentAttempt.id).where(BookingPaymentAttempt.appointment_id==apt.id,BookingPaymentAttempt.state.in_(LIVE)))
        if live and state not in {'paid','payment_received_review'}:state='payment_processing'
        elif state=='unpaid_hold' and apt.hold_expires_at and utc(apt.hold_expires_at)<=now():state='expired_unpaid'
    if service_name is None:service_name=await db.scalar(select(Service.name).where(Service.id==apt.service_id,Service.tenant_id==apt.tenant_id))
    receipt=await receipt_summary(db,apt)
    from app.services.booking_refund_verification import unresolved_refund_verification
    if await unresolved_refund_verification(db,apt.tenant_id,apt.id):state='refund_pending'
    internal={}
    if actor is not None and actor.role in STAFF:
        from app.services.booking_receipt_application import prepayment_view
        internal={'prepayment':await prepayment_view(db,apt),'repair_order_id':str(apt.repair_order_id) if apt.repair_order_id else None,'application_review_required':bool((receipt and (receipt['payment_verification_required'] or (receipt['unapplied_amount'] is not None and Decimal(receipt['unapplied_amount'])>0))) or state=='payment_processing'),'accounting_classification':'booking_prepayment_liability' if receipt else None}
    return {**internal,'id':str(apt.id),'confirmation_number':apt.confirmation_number,'customer_id':str(apt.customer_id),'vehicle_id':str(apt.vehicle_id) if apt.vehicle_id else None,'service_id':str(apt.service_id),'service_name':service_name or 'Service','scheduled_at':apt.scheduled_at,'duration_minutes':apt.duration_minutes,'status':apt.status.value,'price':str(apt.price),'customer_notes':apt.customer_notes,'paid_at':apt.paid_at,'created_at':apt.created_at,'booking_kind':apt.booking_kind,'booking_payment_version':apt.booking_payment_version,'booking_payment_state':state,'hold_expires_at':apt.hold_expires_at,'price_snapshot_sha256':apt.price_snapshot_sha256,'version':apt.booking_version,'currency':apt.booking_currency,'receipt':receipt,'payment_attempt_id':str(latest_attempt.id) if latest_attempt else None,'payment_attempt_state':latest_attempt.state if latest_attempt else None,'payment_provider':latest_attempt.provider if latest_attempt else None}

def binding(attempt):
    return provider.BookingProviderBinding(attempt.provider,attempt.provider_account_id,attempt.configuration_version,attempt.environment,attempt.tenant_id)

def validate_attempt_binding(apt,attempt):
    amount=Decimal(str(apt.price))*100
    if (not amount.is_finite() or amount!=amount.to_integral_value() or attempt.appointment_id!=apt.id or attempt.tenant_id!=apt.tenant_id or attempt.customer_id!=apt.customer_id or attempt.amount_minor!=int(amount) or attempt.configuration_version!=apt.booking_provider_configuration_version or attempt.environment!=apt.booking_provider_environment or attempt.currency!=apt.booking_currency or attempt.currency!='usd'):
        fail('booking_attempt_binding_mismatch','Payment identity needs shop review before this reservation can be confirmed.')

def metadata(apt,attempt):
    return {'purpose':'booking_prepayment_v1','tenant_id':str(apt.tenant_id),'customer_id':str(apt.customer_id),'appointment_id':str(apt.id),'booking_payment_attempt_id':str(attempt.id),'price_snapshot_sha256':apt.price_snapshot_sha256,'provider_account_id':attempt.provider_account_id}

async def attempt_response(db,apt,attempt,*,secret=None):
    view=await snapshot(db,apt)
    return {'attempt_id':str(attempt.id),'provider':attempt.provider,'state':attempt.state,'booking_status':apt.status.value,'booking_payment_state':view['booking_payment_state'],'client_secret':secret,'stripe_account_id':attempt.provider_account_id if attempt.provider=='stripe_connect' else None,'payment_intent_id':attempt.provider_intent_id if attempt.provider=='stripe_connect' else None,'amount':str(Decimal(attempt.amount_minor)/100),'currency':attempt.currency,'hold_expires_at':apt.hold_expires_at,'appointment_version':apt.booking_version,'receipt':view['receipt']}

async def apply_result(db,appointment_id,attempt_id,result,*,source='server_retrieval',event_id=None):
    discovery=await db.get(BookingPaymentAttempt,attempt_id)
    if not discovery: fail('booking_attempt_unavailable','Payment verification is unavailable.')
    tenant_id=discovery.tenant_id
    await locks(db,tenant_id)
    apt=await db.scalar(select(Appointment).where(Appointment.id==appointment_id,Appointment.tenant_id==tenant_id).with_for_update().execution_options(populate_existing=True))
    attempt=await db.scalar(select(BookingPaymentAttempt).where(BookingPaymentAttempt.id==attempt_id,BookingPaymentAttempt.tenant_id==tenant_id,BookingPaymentAttempt.appointment_id==appointment_id).with_for_update().execution_options(populate_existing=True))
    if not apt or not attempt:fail('booking_attempt_unavailable','Payment verification is unavailable.')
    validate_attempt_binding(apt,attempt)
    expected=metadata(apt,attempt)
    if (result.environment!=attempt.environment or result.metadata!=expected or digest(expected)!=attempt.source_metadata_sha256 or result.currency!='usd' or result.amount_minor!=attempt.amount_minor or (attempt.provider_intent_id and result.provider_id!=attempt.provider_intent_id)):
        fail('booking_payment_evidence_mismatch','Payment evidence could not be verified.')
    if event_id and await db.scalar(select(BookingPaymentEvent.id).where(BookingPaymentEvent.provider==attempt.provider,BookingPaymentEvent.provider_account_id==attempt.provider_account_id,BookingPaymentEvent.provider_event_id==event_id)):
        return apt,attempt
    previous=apt.booking_payment_state
    attempt.provider_intent_id=result.provider_id
    attempt.provider_charge_id=result.charge_id
    if result.state=='succeeded':
        if result.amount_received_minor!=attempt.amount_minor or not result.paid_at or not result.charge_id:fail('booking_payment_evidence_mismatch','Payment evidence could not be verified.')
        receipt=await db.scalar(select(BookingReceipt).where(BookingReceipt.attempt_id==attempt.id))
        if receipt is not None and not event_id:
            await db.commit()
            return apt,attempt
        if receipt is None:
            receipt=BookingReceipt(id=uuid4(),tenant_id=apt.tenant_id,appointment_id=apt.id,attempt_id=attempt.id,provider=attempt.provider,provider_account_id=attempt.provider_account_id,provider_intent_id=result.provider_id,charge_id=result.charge_id,amount_received_minor=result.amount_received_minor,currency='usd',received_at=result.paid_at,refunded_amount_minor=0,verification_basis=source,proof_sha256=result.proof_digest)
            db.add(receipt)
            await db.flush()  # receipt must exist before the appointment confirmation FK is assigned
            tenant=await db.get(Tenant,apt.tenant_id)
            paid_at=utc(result.paid_at)
            hold_end=utc(apt.hold_expires_at)
            timely=utc(attempt.created_at)-timedelta(minutes=2)<=paid_at<=hold_end
            # A financially unresolved hold never released its capacity at TTL.
            never_released=hold_end>now() or (apt.booking_payment_state=='payment_processing' and attempt.state in LIVE)
            valid=bool(tenant and tenant.is_active and tenant.deleted_at is None) and apt.status==AppointmentStatus.PENDING and apt.booking_payment_state not in {'expired_unpaid','payment_received_review'} and timely and never_released and not await blocking(db,apt.tenant_id,utc(apt.scheduled_at),utc(apt.scheduled_at)+timedelta(minutes=apt.duration_minutes),exclude=apt.id)
            apt.booking_payment_state='paid' if valid else 'payment_received_review'
            if valid:apt.status=AppointmentStatus.CONFIRMED
            apt.paid_at=result.paid_at
            apt.confirmed_receipt_id=receipt.id
        attempt.state='succeeded'
        attempt.verified_at=now()
    elif attempt.state!='succeeded':
        attempt.state=result.state if result.state in LIVE|{'failed','cancelled'} else 'processing'
        if attempt.state in {'failed','cancelled'} and result.amount_received_minor!=0:
            fail('booking_payment_evidence_mismatch','Unresolved funds require payment review.')
        if attempt.state in {'failed','cancelled'}:
            apt.booking_payment_state='expired_unpaid' if utc(apt.hold_expires_at)<=now() else 'unpaid_hold'
        else:apt.booking_payment_state='payment_processing'
    apt.booking_version=(apt.booking_version or 0)+1
    db.add(BookingPaymentEvent(tenant_id=apt.tenant_id,appointment_id=apt.id,attempt_id=attempt.id,source=source,before_state=previous,after_state=apt.booking_payment_state,event_at=now(),provider=attempt.provider,provider_account_id=attempt.provider_account_id,provider_event_id=event_id,proof_sha256=result.proof_digest))
    if result.state=='succeeded':
        from app.services.booking_application_accounting import ensure_manual_accounting_tasks
        await db.flush()
        await ensure_manual_accounting_tasks(db,receipt=receipt)
    await db.commit()
    return apt,attempt

async def start_attempt(db,actor,appointment_id,body,request_key):
    request_key=key(request_key)
    if actor.role!=UserRole.CUSTOMER:raise HTTPException(404,'Appointment not found')
    await locks(db,actor.tenant_id)
    apt=await admitted_appointment(db,actor,appointment_id,write=True)
    if apt.booking_payment_version!=1:fail('appointment_payment_verification_unavailable','Online payment for this appointment is unavailable. Contact the shop for help.')
    request_hash=digest({'appointment_id':apt.id,'expected_version':body.expected_version,'price_snapshot_sha256':body.price_snapshot_sha256})
    attempt=await db.scalar(select(BookingPaymentAttempt).where(BookingPaymentAttempt.tenant_id==apt.tenant_id,BookingPaymentAttempt.idempotency_key==request_key).with_for_update())
    if attempt:
        validate_attempt_binding(apt,attempt)
        if attempt.appointment_id!=apt.id or attempt.request_sha256!=request_hash:fail('idempotency_key_reused','This key belongs to another payment request.')
        await db.commit()
        if not attempt.provider_intent_id:return await attempt_response(db,apt,attempt)
        try:
            result=await provider.retrieve_booking_payment(db,binding(attempt),attempt.provider_intent_id,expected_metadata=metadata(apt,attempt))
            await db.commit()
            apt,attempt=await apply_result(db,apt.id,attempt.id,result)
            return await attempt_response(db,apt,attempt,secret=result.client_secret)
        except provider.BookingProviderError:return await attempt_response(db,apt,attempt)
    if apt.booking_version!=body.expected_version or apt.price_snapshot_sha256!=body.price_snapshot_sha256:fail('booking_snapshot_changed','Refresh and review your reservation before paying.')
    if apt.status!=AppointmentStatus.PENDING or apt.booking_payment_state!='unpaid_hold' or utc(apt.hold_expires_at)<=now():fail('booking_hold_unavailable','This checkout has expired or payment verification is pending.')
    if await db.scalar(select(BookingPaymentAttempt.id).where(BookingPaymentAttempt.appointment_id==apt.id,BookingPaymentAttempt.state.in_(LIVE))):fail('booking_payment_pending','Payment verification is pending. Do not pay again.')
    tenant=await db.get(Tenant,apt.tenant_id)
    capability=await provider.booking_provider_capability(db,tenant)
    if not capability.available:fail(capability.reason_code or 'booking_payment_unavailable',capability.message)
    chosen=capability.binding
    if chosen.configuration_version!=apt.booking_provider_configuration_version or chosen.environment!=apt.booking_provider_environment:
        fail('booking_provider_changed','The shop payment setup changed. Review a new reservation before paying.')
    if chosen.provider=='quickbooks_payments' and not body.quickbooks_token:fail('booking_payment_token_required','Enter your payment details.',422)
    attempt=BookingPaymentAttempt(id=uuid4(),tenant_id=apt.tenant_id,appointment_id=apt.id,customer_id=apt.customer_id,amount_minor=int(Decimal(apt.price)*100),currency='usd',provider=chosen.provider,provider_account_id=chosen.account_id,configuration_version=chosen.configuration_version,environment=chosen.environment,state='creating',idempotency_key=request_key,request_sha256=request_hash,provider_request_id=f'booking:{uuid4()}')
    validate_attempt_binding(apt,attempt)
    attempt.source_metadata_sha256=digest(metadata(apt,attempt))
    db.add(attempt)
    await db.flush()
    db.add(BookingPaymentEvent(tenant_id=apt.tenant_id,appointment_id=apt.id,attempt_id=attempt.id,actor_user_id=getattr(actor,'id',None),source='payment_attempt',before_state=apt.booking_payment_state,after_state='payment_processing',provider=attempt.provider,provider_account_id=attempt.provider_account_id,event_at=now(),proof_sha256=attempt.source_metadata_sha256))
    apt.booking_payment_state='payment_processing'
    apt.booking_version+=1
    await db.commit()  # durable identity before any external call; no row/advisory locks over I/O
    try:
        result=await provider.create_booking_payment(db,chosen,amount_minor=attempt.amount_minor,currency='usd',metadata=metadata(apt,attempt),idempotency_key=attempt.provider_request_id,quickbooks_token=body.quickbooks_token)
        await db.commit()
        apt,attempt=await apply_result(db,apt.id,attempt.id,result)
        return await attempt_response(db,apt,attempt,secret=result.client_secret)
    except provider.BookingProviderError as exc:
        await db.rollback()
        await locks(db,actor.tenant_id)
        apt=await admitted_appointment(db,actor,appointment_id,write=True)
        attempt=await db.scalar(select(BookingPaymentAttempt).where(BookingPaymentAttempt.tenant_id==apt.tenant_id,BookingPaymentAttempt.appointment_id==apt.id,BookingPaymentAttempt.idempotency_key==request_key).with_for_update())
        if attempt.state!='succeeded':
            attempt.state='outcome_unknown' if exc.outcome_unknown else 'failed'
            known=getattr(exc,'provider_id',None)
            if known and not attempt.provider_intent_id:attempt.provider_intent_id=known
            apt.booking_payment_state='payment_processing' if exc.outcome_unknown else 'expired_unpaid' if utc(apt.hold_expires_at)<=now() else 'unpaid_hold'
            db.add(BookingPaymentEvent(tenant_id=apt.tenant_id,appointment_id=apt.id,attempt_id=attempt.id,source='provider_outcome_unknown' if exc.outcome_unknown else 'provider_failed',after_state=apt.booking_payment_state,event_at=now(),provider=attempt.provider,provider_account_id=attempt.provider_account_id))
            apt.booking_version+=1
        await db.commit()
        return await attempt_response(db,apt,attempt)

async def verify_attempt(db,actor,appointment_id,body):
    apt=await admitted_appointment(db,actor,appointment_id)
    if apt.booking_payment_version!=1:fail('appointment_payment_verification_unavailable','Online payment for this appointment is unavailable. Contact the shop for help.')
    attempt=await db.scalar(select(BookingPaymentAttempt).where(BookingPaymentAttempt.id==body.attempt_id,BookingPaymentAttempt.tenant_id==apt.tenant_id,BookingPaymentAttempt.appointment_id==apt.id))
    if not attempt:raise HTTPException(404,'Payment attempt not found')
    validate_attempt_binding(apt,attempt)
    if body.expected_version!=apt.booking_version and apt.booking_payment_state not in {'paid','payment_received_review','refunded','refund_pending'}:
        fail('booking_snapshot_changed','Refresh your reservation before verifying payment.')
    if not attempt.provider_intent_id:return await attempt_response(db,apt,attempt)
    await db.commit()
    try:result=await provider.retrieve_booking_payment(db,binding(attempt),attempt.provider_intent_id,expected_metadata=metadata(apt,attempt))
    except provider.BookingProviderError:return await attempt_response(db,apt,attempt)
    await db.commit()
    apt,attempt=await apply_result(db,apt.id,attempt.id,result)
    return await attempt_response(db,apt,attempt)

async def expire_holds(db,*,limit=100):
    ids=(await db.scalars(select(Appointment.id).where(Appointment.booking_payment_version==1,Appointment.status==AppointmentStatus.PENDING,Appointment.hold_expires_at<=now(),Appointment.booking_payment_state.in_(['unpaid_hold','payment_processing'])).limit(limit))).all()
    count=0
    for identity in ids:
        discovery=await db.get(Appointment,identity)
        await locks(db,discovery.tenant_id)
        apt=await db.scalar(select(Appointment).where(Appointment.id==identity).with_for_update().execution_options(populate_existing=True))
        if (not apt or apt.booking_payment_version!=1 or apt.status!=AppointmentStatus.PENDING or apt.booking_payment_state not in {'unpaid_hold','payment_processing'} or not apt.hold_expires_at or utc(apt.hold_expires_at)>now() or apt.confirmed_receipt_id is not None):
            await db.commit()
            continue
        live=await db.scalar(select(BookingPaymentAttempt).where(BookingPaymentAttempt.appointment_id==identity,BookingPaymentAttempt.state.in_(LIVE)).with_for_update())
        if not live:
            apt.booking_payment_state='expired_unpaid';apt.booking_version+=1;count+=1
            db.add(BookingPaymentEvent(tenant_id=apt.tenant_id,appointment_id=apt.id,source='expiry',before_state='unpaid_hold',after_state='expired_unpaid',event_at=now()))
            await db.commit();continue
        await db.commit()
        if live.provider_intent_id:
            try:
                result=await provider.cancel_unpaid_booking_payment(db,binding(live),live.provider_intent_id,expected_metadata=metadata(apt,live),idempotency_key=f'booking-expire:{live.id}')
                await db.commit()
                await apply_result(db,apt.id,live.id,result)
            except provider.BookingProviderError:await db.rollback()
    return count

async def dispatch_connect_event(db,event):
    """Only invoke after the Connect-specific signature has been verified."""
    obj=event['data']['object']; kind=event['type']; account=event.get('account')
    intent_id=obj.get('id') if kind.startswith('payment_intent.') else obj.get('payment_intent')
    if isinstance(intent_id,dict):intent_id=intent_id.get('id')
    purpose=(obj.get('metadata') or {}).get('purpose')=='booking_prepayment_v1'
    attempt=await db.scalar(select(BookingPaymentAttempt).where(BookingPaymentAttempt.provider=='stripe_connect',BookingPaymentAttempt.provider_account_id==account,BookingPaymentAttempt.provider_intent_id==intent_id)) if account and intent_id else None
    recovery=False
    if not attempt:
        if not purpose:return False
        fields=obj.get('metadata') or {}
        try:attempt_id=UUID(fields.get('booking_payment_attempt_id',''))
        except (TypeError,ValueError):fail('booking_webhook_unbound','Booking payment evidence is not bound to a stored attempt.')
        attempt=await db.scalar(select(BookingPaymentAttempt).where(BookingPaymentAttempt.id==attempt_id,BookingPaymentAttempt.provider=='stripe_connect',BookingPaymentAttempt.provider_account_id==account,BookingPaymentAttempt.provider_intent_id.is_(None),BookingPaymentAttempt.state.in_(['creating','outcome_unknown'])))
        if not attempt:fail('booking_webhook_unbound','Booking payment evidence is not bound to a stored attempt.')
        recovery=True
    apt=await db.get(Appointment,attempt.appointment_id)
    if recovery and (obj.get('metadata')!=metadata(apt,attempt) or digest(obj.get('metadata'))!=attempt.source_metadata_sha256):fail('booking_webhook_unbound','Booking payment evidence does not match its stored attempt.')
    if bool(event.get('livemode')) != (attempt.environment=='production'):fail('booking_webhook_environment','Booking payment environment does not match.')
    await db.commit()
    if kind in {'payment_intent.succeeded','payment_intent.payment_failed','payment_intent.processing','payment_intent.canceled','payment_intent.requires_action'}:
        if recovery:
            result=await provider.recover_created_booking_payment(db,binding(attempt),amount_minor=attempt.amount_minor,currency=attempt.currency,metadata=metadata(apt,attempt),idempotency_key=attempt.provider_request_id,attempt_created_at=attempt.created_at,expected_provider_id=intent_id)
            if result.provider_id!=intent_id:fail('booking_webhook_unbound','Payment identity needs shop review.')
            await db.commit()
        else:
            result=await provider.retrieve_booking_payment(db,binding(attempt),intent_id,expected_metadata=metadata(apt,attempt))
            await db.commit()
        if result.state=='canceled':
            from dataclasses import replace
            result=replace(result,state='cancelled')
        await apply_result(db,apt.id,attempt.id,result,source='verified_connect_webhook',event_id=event['id'])
    elif kind=='charge.refunded':
        await locks(db,apt.tenant_id)
        apt=await db.scalar(select(Appointment).where(Appointment.id==apt.id).with_for_update().execution_options(populate_existing=True))
        receipt=await db.scalar(select(BookingReceipt).where(BookingReceipt.attempt_id==attempt.id,BookingReceipt.provider_account_id==account,BookingReceipt.provider_intent_id==intent_id).with_for_update().execution_options(populate_existing=True))
        if not receipt:fail('booking_receipt_unavailable','Booking receipt not yet verified.')
        if await db.scalar(select(BookingPaymentEvent.id).where(BookingPaymentEvent.provider=='stripe_connect',BookingPaymentEvent.provider_account_id==account,BookingPaymentEvent.provider_event_id==event['id'])):return True
        refunded=obj.get('amount_refunded')
        if (obj.get('id')!=receipt.charge_id or obj.get('currency')!='usd' or obj.get('amount')!=receipt.amount_received_minor or not isinstance(refunded,int) or isinstance(refunded,bool) or not 0<=refunded<=receipt.amount_received_minor):fail('booking_refund_mismatch','Booking refund evidence could not be verified.')
        previous_refunded=receipt.refunded_amount_minor
        actual_refunded=max(refunded,previous_refunded)
        after_state='refunded' if actual_refunded==receipt.amount_received_minor else 'refund_pending' if actual_refunded else apt.booking_payment_state
        refund_event=BookingPaymentEvent(tenant_id=apt.tenant_id,appointment_id=apt.id,attempt_id=attempt.id,source='verified_connect_webhook',after_state=after_state,provider='stripe_connect',provider_account_id=account,provider_event_id=event['id'],event_at=now(),verified_refund_amount_minor=actual_refunded,proof_sha256=digest({'charge':obj['id'],'refunded':refunded}))
        db.add(refund_event)
        await db.flush()  # durable provider evidence must precede aggregate change
        receipt.refunded_amount_minor=actual_refunded
        if actual_refunded!=previous_refunded:
            receipt.version+=1
            apt.booking_payment_state=after_state
            apt.booking_version+=1
        await db.flush()
        if receipt.refunded_amount_minor!=previous_refunded:
            from app.services.booking_application_accounting import mark_manual_accounting_needs_review
            await mark_manual_accounting_needs_review(db,tenant_id=apt.tenant_id,receipt_id=receipt.id,source_event_id=refund_event.id,reason='Verified booking refund changed prepaid liability.')
            from app.services.booking_receipt_application import invalidate_application_settlements
            await invalidate_application_settlements(db,apt.tenant_id,receipt.id)
        await db.commit()
    elif kind in {'charge.dispute.created','charge.dispute.updated','charge.dispute.closed'}:
        await locks(db,apt.tenant_id)
        apt=await db.scalar(select(Appointment).where(Appointment.id==apt.id,Appointment.tenant_id==attempt.tenant_id).with_for_update().execution_options(populate_existing=True))
        receipt=await db.scalar(select(BookingReceipt).where(BookingReceipt.tenant_id==apt.tenant_id,BookingReceipt.attempt_id==attempt.id).with_for_update().execution_options(populate_existing=True))
        if not receipt:fail('booking_receipt_unavailable','Booking receipt not yet verified.')
        if await db.scalar(select(BookingPaymentEvent.id).where(BookingPaymentEvent.provider=='stripe_connect',BookingPaymentEvent.provider_account_id==account,BookingPaymentEvent.provider_event_id==event['id'])):return True
        amount=obj.get('amount');charge=obj.get('charge');charge=charge.get('id') if isinstance(charge,dict) else charge
        if charge!=receipt.charge_id or obj.get('currency')!='usd' or not isinstance(amount,int) or isinstance(amount,bool) or not 0<amount<=receipt.amount_received_minor:
            fail('booking_dispute_mismatch','Booking dispute evidence could not be verified.')
        dispute_event=BookingPaymentEvent(tenant_id=apt.tenant_id,appointment_id=apt.id,attempt_id=attempt.id,source='verified_connect_webhook',after_state='payment_received_review',provider='stripe_connect',provider_account_id=account,provider_event_id=event['id'],event_at=now(),verified_dispute_amount_minor=amount,proof_sha256=digest({'dispute':obj.get('id'),'charge':charge,'amount':amount,'status':obj.get('status')}))
        db.add(dispute_event);await db.flush()
        apt.booking_payment_state='payment_received_review';apt.booking_version+=1;receipt.version+=1
        await db.flush()
        from app.services.booking_application_accounting import mark_manual_accounting_needs_review
        from app.services.booking_receipt_application import invalidate_application_settlements
        await mark_manual_accounting_needs_review(db,tenant_id=apt.tenant_id,receipt_id=receipt.id,source_event_id=dispute_event.id,reason='Verified booking dispute requires financial review.')
        await invalidate_application_settlements(db,apt.tenant_id,receipt.id)
        await db.commit()
    return True


async def reconcile_live_attempts(db,*,limit=50):
    """Verify stored provider identities before TTL; never creates/cancels/refunds."""
    identities=(await db.scalars(select(BookingPaymentAttempt.id).where(BookingPaymentAttempt.state.in_(LIVE),BookingPaymentAttempt.provider_intent_id.is_not(None)).order_by(BookingPaymentAttempt.updated_at).limit(limit))).all()
    await db.commit()
    verified=0
    for identity in identities:
        attempt=await db.get(BookingPaymentAttempt,identity)
        apt=await db.get(Appointment,attempt.appointment_id)
        if not apt or apt.booking_payment_version!=1:continue
        expected=metadata(apt,attempt);bound=binding(attempt);provider_id=attempt.provider_intent_id;appointment_id=apt.id
        await db.commit()
        try:
            result=await provider.retrieve_booking_payment(db,bound,provider_id,expected_metadata=expected)
            await db.commit()
            await apply_result(db,appointment_id,identity,result)
            verified+=1
        except (provider.BookingProviderError,HTTPException):
            await db.rollback()
    return verified
