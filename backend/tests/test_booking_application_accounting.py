from decimal import Decimal
from uuid import uuid4
import pytest
from sqlalchemy import select, func
from app.db.models.booking_application import BookingReceiptApplication, BookingAccountingReviewTask, BookingAccountingReviewEvent
from app.db.models.booking_payment import BookingReceipt
from app.db.models.appointment import Appointment, AppointmentStatus
from app.db.models.invoice import Invoice, InvoiceStatus
from app.db.models.invoice_settlement import InvoiceSettlement
from app.db.models.user import User
from app.db.models.payment import Payment
from app.services import booking_application_accounting as accounting
from app.services.invoice_settlement_service import SettlementDomainError
from tests.test_booking_invoice_guard import seed

async def context(db,amount=4000,application_created_at=None,charge_binding="valid"):
    t,ro=await seed(db,'succeeded',0,charge_binding=charge_binding)
    r=await db.scalar(select(BookingReceipt).where(BookingReceipt.tenant_id==t.id))
    apt=await db.scalar(select(Appointment).where(Appointment.id==r.appointment_id))
    owner=await db.scalar(select(User).where(User.tenant_id==t.id))
    apt.status=AppointmentStatus.CONFIRMED;apt.booking_payment_state='paid';apt.confirmed_receipt_id=r.id
    await db.flush()
    inv=Invoice(tenant_id=t.id,repair_order_id=ro.id,billed_customer_id=ro.customer_id,invoice_number=str(uuid4()),status=InvoiceStatus.SENT,subtotal=100,total_amount=100,tax_amount=0,discount_amount=0)
    db.add(inv);await db.flush()
    settlement=InvoiceSettlement(tenant_id=t.id,invoice_id=inv.id,customer_id=ro.customer_id,principal_total=100)
    db.add(settlement);await db.flush()
    app=BookingReceiptApplication(created_at=application_created_at,tenant_id=t.id,receipt_id=r.id,appointment_id=apt.id,repair_order_id=ro.id,invoice_id=inv.id,settlement_id=settlement.id,customer_id=ro.customer_id,amount_minor=amount,currency='usd',receipt_version_before=r.version,booking_version_before=apt.booking_version,provider='quickbooks_payments',provider_account_id='realm',environment='sandbox',configuration_version=1,qbo_realm_snapshot='realm',receipt_proof_sha256=r.proof_sha256,invoice_economics_sha256='d'*64,actor_user_id=owner.id,actor_name_snapshot='Owner',idempotency_key=str(uuid4()),request_sha256='e'*64)
    db.add(app);await db.flush()
    return t,r,apt,owner,inv,app

async def ack(db,ctx,task,**changes):
    t,r,apt,owner,inv,app=ctx
    values=dict(tenant_id=t.id,appointment_id=apt.id,task_id=task.id,actor=owner,expected_version=1,idempotency_key='ack-'+str(task.id),evidence_reference='journal-123',external_company_reference='realm',review_note='Reviewed actual external ledger',receipt_liability_recorded=True,application_to_ar_recorded=task.object_kind=='booking_receipt_application')
    values.update(changes)
    return await accounting.acknowledge_manual_accounting(db,**values)

@pytest.mark.asyncio
async def test_canonical_amounts_exact_hold_no_new_cash(db_session):
    t,r,apt,owner,inv,app=await context(db_session)
    tasks=await accounting.ensure_manual_accounting_tasks(db_session,receipt=r,application=app)
    again=await accounting.ensure_manual_accounting_tasks(db_session,receipt=r,application=app)
    assert [x.id for x in tasks]==[x.id for x in again]
    assert await accounting.receipt_balances(db_session,t.id,r.id)==dict(received_minor=10000,refunded_minor=0,applied_minor=4000,unapplied_minor=6000,version=1)
    assert await accounting.applied_principal_for_invoice(db_session,t.id,inv.id)==Decimal('40.00')
    assert await accounting.applied_principal_for_invoice(db_session,uuid4(),inv.id)==0
    assert await accounting.invoice_has_booking_export_hold(db_session,t.id,inv.id)
    assert not await accounting.invoice_has_booking_export_hold(db_session,uuid4(),inv.id)
    assert not await accounting.invoice_has_booking_export_hold(db_session,t.id,uuid4())
    assert await db_session.scalar(select(func.count()).select_from(Payment))==0

@pytest.mark.asyncio
async def test_ack_replay_is_audit_not_export_success(db_session):
    ctx=await context(db_session)
    tasks=await accounting.ensure_manual_accounting_tasks(db_session,receipt=ctx[1],application=ctx[-1])
    await ack(db_session,ctx,tasks[0]);await ack(db_session,ctx,tasks[1]);await ack(db_session,ctx,tasks[1])
    assert all(x.state=='externally_reconciled' and x.version==2 for x in tasks)
    assert await db_session.scalar(select(func.count()).select_from(BookingAccountingReviewEvent))==2
    assert await accounting.invoice_has_booking_export_hold(db_session,ctx[0].id,ctx[-2].id)
    with pytest.raises(SettlementDomainError) as e:await ack(db_session,ctx,tasks[1],review_note='Changed')
    assert e.value.code=='idempotency_conflict'

@pytest.mark.asyncio
async def test_application_ack_requires_prior_liability_ack(db_session):
    ctx=await context(db_session)
    tasks=await accounting.ensure_manual_accounting_tasks(db_session,receipt=ctx[1],application=ctx[-1])
    with pytest.raises(SettlementDomainError) as e:await ack(db_session,ctx,tasks[1])
    assert e.value.code=='booking_liability_ack_required'

@pytest.mark.asyncio
@pytest.mark.parametrize('changes,code',[({'tenant_id':uuid4()},'booking_accounting_review_not_found'),({'appointment_id':uuid4()},'booking_accounting_review_not_found'),({'evidence_reference':''},'booking_accounting_evidence_required'),({'receipt_liability_recorded':False},'booking_accounting_evidence_required'),({'expected_version':99},'booking_accounting_version_conflict')])
async def test_ack_rejects_invalid_evidence(db_session,changes,code):
    ctx=await context(db_session)
    tasks=await accounting.ensure_manual_accounting_tasks(db_session,receipt=ctx[1],application=ctx[-1])
    with pytest.raises(SettlementDomainError) as e:await ack(db_session,ctx,tasks[0],**changes)
    assert e.value.code==code and tasks[0].state=='awaiting_manual_ack'

@pytest.mark.asyncio
async def test_application_append_only(db_session):
    ctx=await context(db_session);ctx[-1].amount_minor=1
    with pytest.raises(ValueError,match='append-only'):await db_session.flush()

@pytest.mark.asyncio
async def test_missing_task_does_not_release_export(db_session):
    ctx=await context(db_session)
    assert await accounting.invoice_has_booking_export_hold(db_session,ctx[0].id,ctx[-2].id)

@pytest.mark.asyncio
async def test_provider_change_retains_ack_and_append_only_source_audit(db_session):
    from datetime import datetime,timezone
    from app.db.models.booking_payment import BookingPaymentEvent
    ctx=await context(db_session)
    tasks=await accounting.ensure_manual_accounting_tasks(db_session,receipt=ctx[1],application=ctx[-1])
    await ack(db_session,ctx,tasks[0]);await ack(db_session,ctx,tasks[1])
    event=BookingPaymentEvent(id=uuid4(),tenant_id=ctx[0].id,appointment_id=ctx[2].id,
        attempt_id=ctx[1].attempt_id,source='server_retrieval',after_state='refund_pending',
        provider=ctx[1].provider,provider_account_id=ctx[1].provider_account_id,
        event_at=datetime.now(timezone.utc),proof_sha256='f'*64)
    db_session.add(event);await db_session.flush()
    for _ in range(2):
        await accounting.mark_manual_accounting_needs_review(db_session,tenant_id=ctx[0].id,
            receipt_id=ctx[1].id,source_event_id=event.id,reason='Verified provider refund')
    assert all(task.state=='needs_review' and task.version==3 for task in tasks)
    assert await db_session.scalar(select(func.count()).select_from(BookingAccountingReviewEvent))==4
    assert await accounting.invoice_has_booking_export_hold(db_session,ctx[0].id,ctx[-2].id)


@pytest.mark.asyncio
@pytest.mark.parametrize('charge_binding',['missing_receipt','missing_attempt','empty_receipt','empty_attempt','mismatch'])
async def test_receipt_source_rejects_missing_or_wrong_charge(db_session,charge_binding):
    t,ro=await seed(db_session,'succeeded',0,charge_binding=charge_binding)
    receipt=await db_session.scalar(select(BookingReceipt).where(BookingReceipt.tenant_id==t.id))
    with pytest.raises(SettlementDomainError) as error:
        await accounting.ensure_manual_accounting_tasks(db_session,receipt=receipt)
    assert error.value.code=='booking_receipt_proof_invalid'
    assert await db_session.scalar(select(func.count()).select_from(BookingAccountingReviewTask))==0
