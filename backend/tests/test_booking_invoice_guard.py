from datetime import datetime, timezone, timedelta
from uuid import uuid4
from types import SimpleNamespace
import pytest
from app.db.models.tenant import Tenant
from app.db.models.customer import Customer
from app.db.models.vehicle import Vehicle
from app.db.models.repair_order import RepairOrder
from app.db.models.service import Service
from app.db.models.appointment import Appointment
from app.db.models.booking_payment import BookingPaymentAttempt, BookingReceipt
from app.services.booking_invoice_guard import require_booking_prepayment_resolved
from app.services.invoice_settlement_service import SettlementDomainError

async def reservation_snapshot(db, tenant):
    from sqlalchemy import select
    from app.db.models.invoice_settlement import TenantPaymentProviderConfiguration
    from app.db.models.user import User, UserRole
    config=await db.scalar(select(TenantPaymentProviderConfiguration).where(
        TenantPaymentProviderConfiguration.tenant_id==tenant.id,
        TenantPaymentProviderConfiguration.version==1))
    if config is None:
        owner=User(tenant_id=tenant.id,email=f'{uuid4()}@example.com',hashed_password='test',
            first_name='Guard',last_name='Owner',role=UserRole.GARAGE_OWNER)
        db.add(owner);await db.flush()
        config=TenantPaymentProviderConfiguration(tenant_id=tenant.id,version=1,
            selected_provider='quickbooks_payments',readiness_state='ready',actor_user_id=owner.id,
            actor_name_snapshot='Guard Owner',provider_account_snapshot='realm',
            qbo_realm_snapshot='realm',writer_strategy='dieselbridge',
            idempotency_key=str(uuid4()),request_hash='d'*64)
        db.add(config);await db.flush()
    return dict(booking_kind='reserve',booking_version=1,
        hold_expires_at=datetime.now(timezone.utc)-timedelta(minutes=1),
        price_snapshot_sha256='a'*64,booking_idempotency_key=str(uuid4()),
        booking_request_sha256='b'*64,booking_currency='usd',
        booking_provider_configuration_version=config.version,booking_provider_environment='sandbox')


async def seed(db,state=None,refund=None):
    t=Tenant(name='Guard',slug=str(uuid4()))
    c=Customer(tenant=t,first_name='Guard',last_name='Customer',email='guard@example.com')
    v=Vehicle(tenant=t,customer=c,make='Demo',model='Truck',vin=uuid4().hex[:17])
    ro=RepairOrder(tenant=t,customer=c,vehicle=v,order_number=str(uuid4()))
    svc=Service(tenant=t,name='Service')
    db.add_all([ro,svc]);await db.flush()
    apt=Appointment(tenant_id=t.id,customer_id=c.id,service_id=svc.id,repair_order_id=ro.id,
        scheduled_at=datetime.now(timezone.utc),duration_minutes=60,price=100,
        confirmation_number=uuid4().hex[:20],booking_payment_version=1,booking_payment_state='expired_unpaid',**(await reservation_snapshot(db,t)))
    db.add(apt);await db.flush()
    if state:
        a=BookingPaymentAttempt(tenant_id=t.id,appointment_id=apt.id,customer_id=c.id,
            amount_minor=10000,currency='usd',provider='quickbooks_payments',provider_account_id='realm',
            configuration_version=1,environment='sandbox',source_metadata_sha256='a'*64,
            provider_intent_id=str(uuid4()),provider_request_id=str(uuid4()),state=state,
            idempotency_key=str(uuid4()),request_sha256='b'*64,
            verified_at=datetime.now(timezone.utc) if state=='succeeded' else None)
        db.add(a);await db.flush()
        if refund is not None:
            db.add(BookingReceipt(tenant_id=t.id,appointment_id=apt.id,attempt_id=a.id,
                provider=a.provider,provider_account_id=a.provider_account_id,provider_intent_id=a.provider_intent_id,
                amount_received_minor=10000,currency='usd',received_at=datetime.now(timezone.utc),
                refunded_amount_minor=refund,verification_basis='server_retrieval',proof_sha256='c'*64))
    await db.commit();return t,ro

@pytest.mark.asyncio
@pytest.mark.parametrize('state,refund',[('succeeded',0),('succeeded',5000),('succeeded',None),('processing',None),('creating',None),('outcome_unknown',None),('requires_action',None)])
async def test_exact_unresolved_link_blocks_read_only(db_session,state,refund):
    t,ro=await seed(db_session,state,refund)
    with pytest.raises(SettlementDomainError) as e:
        await require_booking_prepayment_resolved(db_session,t.id,ro.id)
    assert e.value.code=='booking_prepayment_review_required' and e.value.status_code==409
    assert not db_session.new and not db_session.dirty and not db_session.deleted

@pytest.mark.asyncio
@pytest.mark.parametrize('state,refund',[(None,None),('failed',None),('cancelled',None),('succeeded',10000)])
async def test_no_funds_or_full_refund_passes(db_session,state,refund):
    t,ro=await seed(db_session,state,refund)
    await require_booking_prepayment_resolved(db_session,t.id,ro.id)

@pytest.mark.asyncio
async def test_exact_tenant_and_order_not_customer_match(db_session):
    t,ro=await seed(db_session,'succeeded',0)
    other=RepairOrder(tenant_id=t.id,customer_id=ro.customer_id,vehicle_id=ro.vehicle_id,order_number=str(uuid4()))
    db_session.add(other);await db_session.commit()
    await require_booking_prepayment_resolved(db_session,t.id,other.id)
    await require_booking_prepayment_resolved(db_session,uuid4(),ro.id)

@pytest.mark.asyncio
async def test_verified_provider_callback_skips_admission(monkeypatch):
    from app.services import invoice_accounting_policy as policy
    async def standard(*a,**k):return 'standard'
    async def forbidden(*a,**k):raise AssertionError('callback cannot invoke admission guard')
    monkeypatch.setattr(policy,'locked_policy',standard)
    monkeypatch.setattr('app.services.booking_invoice_guard.require_booking_prepayment_resolved',forbidden)
    await policy.require_standard_payment(None,SimpleNamespace(),new_entry=True,verified_provider_fact=True)

@pytest.mark.asyncio
@pytest.mark.parametrize('manual',[False,True])
async def test_invoice_issuance_blocks_before_creating_invoice(db_session,manual):
    from app.api.v1.endpoints.invoices import auto_create_invoice_for_order, create_invoice, InvoiceCreate
    from app.db.models.repair_order import RepairOrderStatus
    from app.db.models.user import UserRole
    from app.db.models.invoice import Invoice
    from sqlalchemy import select, func
    t,ro=await seed(db_session,'succeeded',0)
    ro.status=RepairOrderStatus.COMPLETED
    await db_session.commit()
    with pytest.raises(SettlementDomainError) as e:
        if manual:
            await create_invoice(InvoiceCreate(repair_order_id=ro.id),db_session,
                SimpleNamespace(role=UserRole.GARAGE_OWNER,tenant_id=t.id))
        else:
            await auto_create_invoice_for_order(db_session,ro,t,notify=False)
    assert e.value.code=='booking_prepayment_review_required'
    assert await db_session.scalar(select(func.count()).select_from(Invoice))==0
    assert not db_session.new and not db_session.dirty

@pytest.mark.asyncio
async def test_central_new_payment_entry_uses_guard(db_session,monkeypatch):
    from app.services import invoice_accounting_policy as policy
    t,ro=await seed(db_session,'succeeded',0)
    async def standard(*a,**k):return 'standard'
    monkeypatch.setattr(policy,'locked_policy',standard)
    with pytest.raises(SettlementDomainError) as e:
        await policy.require_standard_payment(db_session,
            SimpleNamespace(tenant_id=t.id,repair_order_id=ro.id),new_entry=True)
    assert e.value.code=='booking_prepayment_review_required'

@pytest.mark.asyncio
@pytest.mark.parametrize('corruption',['receipt_proof','receipt_provider','deleted_appointment'])
async def test_deleted_or_invalid_evidence_never_releases_funds(db_session,corruption):
    from sqlalchemy import select
    t,ro=await seed(db_session,'succeeded',10000 if corruption!='deleted_appointment' else 0)
    if corruption=='deleted_appointment':
        apt=await db_session.scalar(select(Appointment).where(Appointment.repair_order_id==ro.id))
        apt.deleted_at=datetime.now(timezone.utc)
    else:
        receipt=await db_session.scalar(select(BookingReceipt).where(BookingReceipt.tenant_id==t.id))
        if corruption=='receipt_proof':receipt.proof_sha256=''
        else:receipt.provider_account_id='wrong-account'
    await db_session.commit()
    with pytest.raises(SettlementDomainError):
        await require_booking_prepayment_resolved(db_session,t.id,ro.id)

@pytest.mark.asyncio
async def test_new_cash_receipt_cannot_double_collect(db_session,monkeypatch):
    from tests.test_db048_cash import context, pay
    from app.db.models.payment import Payment
    from sqlalchemy import select, func
    ctx=await context(db_session,monkeypatch)
    t,owner,c,invoice,_=ctx
    svc=Service(tenant=t,name='Prepaid')
    db_session.add(svc);await db_session.flush()
    apt=Appointment(tenant_id=t.id,customer_id=c.id,service_id=svc.id,repair_order_id=invoice.repair_order_id,
        scheduled_at=datetime.now(timezone.utc),duration_minutes=60,price=100,
        confirmation_number=uuid4().hex[:20],booking_payment_version=1,booking_payment_state='payment_processing',**(await reservation_snapshot(db_session,t)))
    db_session.add(apt);await db_session.flush()
    db_session.add(BookingPaymentAttempt(tenant_id=t.id,appointment_id=apt.id,customer_id=c.id,
        amount_minor=10000,currency='usd',provider='stripe_connect',provider_account_id=t.stripe_account_id,
        configuration_version=1,environment='sandbox',source_metadata_sha256='a'*64,
        provider_request_id=str(uuid4()),state='outcome_unknown',idempotency_key=str(uuid4()),request_sha256='b'*64))
    await db_session.flush()
    with pytest.raises(SettlementDomainError) as e:
        await pay(db_session,ctx)
    assert e.value.code=='booking_prepayment_review_required'
    assert await db_session.scalar(select(func.count()).select_from(Payment))==0
