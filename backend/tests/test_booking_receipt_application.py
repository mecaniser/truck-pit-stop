from decimal import Decimal
from uuid import uuid4
from unittest.mock import AsyncMock
import pytest
from sqlalchemy import select,func,text
from app.db.models.labor import Labor
from app.db.models.invoice import Invoice
from app.db.models.payment import Payment
from app.db.models.repair_order import RepairOrderStatus
from app.db.models.invoice_settlement import InvoiceSettlement
from app.db.models.booking_application import BookingReceiptApplication,BookingAccountingReviewTask
from app.api.v1.endpoints.appointments import BookingRepairOrderLinkBody,BookingReceiptApplyBody
from app.services import booking_fulfillment as fulfillment
from app.services.booking_receipt_application import prepayment_view,issue_and_apply
from app.services.invoice_settlement_service import SettlementDomainError
from test_booking_fulfillment import staff_user,paid,vehicle_order
from test_verified_booking_flow import setup_booking

async def prepared(db,setup,staff,monkeypatch):
    apt=await paid(db,setup,monkeypatch)
    vehicle,order=await vehicle_order(db,setup)
    await fulfillment.link_appointment(db,staff,apt.id,BookingRepairOrderLinkBody(repair_order_id=order.id,expected_booking_version=apt.booking_version,expected_vehicle_id=vehicle.id,reason='Reviewed intake vehicle'),'c-link-synthetic')
    order.status=RepairOrderStatus.COMPLETED
    db.add(Labor(tenant_id=setup[0].id,repair_order_id=order.id,description='Actual labor',hours=Decimal('1'),hourly_rate=Decimal('150'),total_cost=Decimal('150')))
    await db.commit()
    return apt,order

@pytest.mark.asyncio
async def test_read_preview_is_pure_uses_actual_lines_and_hash_changes_on_repricing(db_session,setup_booking,staff_user,monkeypatch):
    apt,order=await prepared(db_session,setup_booking,staff_user,monkeypatch)
    view=await prepayment_view(db_session,apt)
    assert view['can_apply'] and view['invoice_preview']['allocatable_principal_minor']==15000
    assert view['invoice_preview']['suggested_apply_minor']==12000
    assert await db_session.scalar(select(func.count(Invoice.id)))==0
    assert await db_session.scalar(select(func.count(BookingReceiptApplication.id)))==0
    line=await db_session.scalar(select(Labor));line.hourly_rate=Decimal('175');line.total_cost=Decimal('175');await db_session.commit()
    updated=await prepayment_view(db_session,apt)
    assert updated['invoice_preview']['invoice_economics_sha256']!=view['invoice_preview']['invoice_economics_sha256']

@pytest.mark.asyncio
async def test_changed_economics_rejects_before_invoice_or_application(db_session,setup_booking,staff_user,monkeypatch):
    apt,order=await prepared(db_session,setup_booking,staff_user,monkeypatch)
    view=await prepayment_view(db_session,apt)
    body=BookingReceiptApplyBody(repair_order_id=order.id,receipt_id=apt.confirmed_receipt_id,expected_booking_version=apt.booking_version,expected_receipt_version=1,amount_minor=12000,expected_invoice_economics_sha256='0'*64,accounting_mode='external_manual')
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as err:await issue_and_apply(db_session,staff_user,apt.id,body,'changed-price')
    assert err.value.detail['code']=='booking_invoice_economics_changed'
    assert await db_session.scalar(select(func.count(Invoice.id)))==0
    assert await db_session.scalar(select(func.count(BookingReceiptApplication.id)))==0

@pytest.mark.asyncio
async def test_issue_apply_is_one_genuine_sale_and_no_new_tender_with_replay(db_session,setup_booking,staff_user,monkeypatch):
    apt,order=await prepared(db_session,setup_booking,staff_user,monkeypatch)
    import app.services.service_checklist as checklist
    import app.api.v1.endpoints.invoices as invoices
    import app.services.fleet_financial_wakeup as wakeup
    monkeypatch.setattr(checklist,'guard_completion',AsyncMock())
    monkeypatch.setattr(invoices,'enqueue_invoice_created_email',AsyncMock(return_value=False))
    monkeypatch.setattr(invoices,'enqueue_quickbooks_invoice_sync',AsyncMock())
    monkeypatch.setattr(wakeup,'enqueue_financial_wakeup',AsyncMock())
    monkeypatch.setattr(wakeup,'enqueue_settlement_wakeup',AsyncMock())
    view=await prepayment_view(db_session,apt)
    body=BookingReceiptApplyBody(repair_order_id=order.id,receipt_id=apt.confirmed_receipt_id,expected_booking_version=apt.booking_version,expected_receipt_version=1,amount_minor=12000,expected_invoice_economics_sha256=view['invoice_preview']['invoice_economics_sha256'],accounting_mode='external_manual')
    response=await issue_and_apply(db_session,staff_user,apt.id,body,'apply-once')
    assert response['receipt']['applied_minor']==12000 and response['receipt']['unapplied_minor']==0
    assert response['invoice_payment_summary']['applied_amount']=='120.00', response
    assert await db_session.scalar(select(func.count(Invoice.id)))==1
    assert await db_session.scalar(select(func.count(Payment.id)))==0
    assert await db_session.scalar(select(func.count(BookingReceiptApplication.id)))==1
    assert await db_session.scalar(select(func.count(BookingAccountingReviewTask.id)))==2
    settlement=await db_session.scalar(select(InvoiceSettlement));assert settlement.confirmed_principal==Decimal('120')
    replay=await issue_and_apply(db_session,staff_user,apt.id,body,'apply-once')
    assert replay['application_id']==response['application_id']
    assert response['invoice_payment_summary']['prepayment_applied_amount']=='120.00'
    # A partially prepaid invoice must never fall through to legacy full-price charging.
    setup_booking[0].stripe_account_id='acct_synthetic';setup_booking[0].stripe_onboarding_complete=True
    await db_session.commit()
    from app.api.v1.endpoints.payments import create_payment_intent_for_invoice,PaymentIntentRequest
    with pytest.raises(SettlementDomainError) as denied:
        await create_payment_intent_for_invoice(PaymentIntentRequest(invoice_id=response['invoice_id']),None,db_session,setup_booking[3])
    assert denied.value.code=='split_payments_disabled'
    from app.api.v1.endpoints.quickbooks import _invoice_outstanding_amount
    invoice=await db_session.scalar(select(Invoice))
    with pytest.raises(SettlementDomainError) as denied:await _invoice_outstanding_amount(db_session,invoice)
    assert denied.value.code=='booking_canonical_settlement_required'
    from types import SimpleNamespace
    import app.api.v1.endpoints.invoice_settlements as settlement_api
    from app.services.invoice_payment_presentation import load_payment_summary
    pending=SimpleNamespace(id=uuid4(),invoice_id=invoice.id,tenant_id=invoice.tenant_id,rail='card',provider='quickbooks_payments',state='pending',version=1,provider_charge_id=None)
    monkeypatch.setattr(settlement_api,'quickbooks_payments_enabled_for_tenant',lambda tenant:True)
    capture=AsyncMock();monkeypatch.setattr(settlement_api,'create_quickbooks_charge',capture)
    apt.booking_payment_state='payment_received_review';settlement.version+=1;await db_session.commit()
    summary=await load_payment_summary(db_session,invoice)
    assert summary.state=='unknown' and summary.payment_verification_required and summary.applied_amount is None
    with pytest.raises(SettlementDomainError) as denied:
        await settlement_api.charge_quickbooks_settlement_attempt(db_session,attempt=pending,invoice=invoice,tenant=setup_booking[0],actor=staff_user,payment_token='late-token',expected_attempt_version=1,idempotency_key='late-card-token')
    assert denied.value.code=='booking_application_verification_required'
    capture.assert_not_awaited()

@pytest.mark.asyncio
async def test_task_failure_rolls_back_invoice_application_and_settlement(db_session,setup_booking,staff_user,monkeypatch):
    apt,order=await prepared(db_session,setup_booking,staff_user,monkeypatch)
    import app.services.service_checklist as checklist
    import app.services.booking_receipt_application as applications
    monkeypatch.setattr(checklist,'guard_completion',AsyncMock())
    monkeypatch.setattr(applications,'ensure_manual_accounting_tasks',AsyncMock(side_effect=RuntimeError('synthetic task failure')))
    view=await prepayment_view(db_session,apt)
    body=BookingReceiptApplyBody(repair_order_id=order.id,receipt_id=apt.confirmed_receipt_id,expected_booking_version=apt.booking_version,expected_receipt_version=1,amount_minor=12000,expected_invoice_economics_sha256=view['invoice_preview']['invoice_economics_sha256'],accounting_mode='external_manual')
    # SQLite legacy transaction mode does not start a transaction for SELECT.
    await db_session.execute(text('BEGIN'))
    with pytest.raises(RuntimeError,match='synthetic task failure'):await issue_and_apply(db_session,staff_user,apt.id,body,'rollback-application')
    await db_session.rollback()
    assert await db_session.scalar(select(func.count(Invoice.id)))==0
    assert await db_session.scalar(select(func.count(InvoiceSettlement.id)))==0
    assert await db_session.scalar(select(func.count(BookingReceiptApplication.id)))==0
    assert await db_session.scalar(select(func.count(Payment.id)))==0

@pytest.mark.parametrize('field,value',[('amount_minor',True),('amount_minor',1.5),('expected_booking_version',True),('expected_receipt_version',1.1)])
def test_apply_contract_rejects_non_integer_money_and_versions(field,value):
    from pydantic import ValidationError
    values=dict(repair_order_id=uuid4(),receipt_id=uuid4(),expected_booking_version=1,expected_receipt_version=1,amount_minor=1,expected_invoice_economics_sha256='a'*64,accounting_mode='external_manual')
    values[field]=value
    with pytest.raises(ValidationError):BookingReceiptApplyBody(**values)

@pytest.mark.asyncio
@pytest.mark.parametrize('fault',['over_receipt','over_invoice','wrong_receipt','foreign_role','stale_booking','stale_receipt'])
async def test_negative_application_admission_writes_no_sale(db_session,setup_booking,staff_user,monkeypatch,fault):
    apt,order=await prepared(db_session,setup_booking,staff_user,monkeypatch)
    view=await prepayment_view(db_session,apt)
    values=dict(repair_order_id=order.id,receipt_id=apt.confirmed_receipt_id,expected_booking_version=apt.booking_version,expected_receipt_version=1,amount_minor=12000,expected_invoice_economics_sha256=view['invoice_preview']['invoice_economics_sha256'],accounting_mode='external_manual')
    actor=staff_user
    if fault=='over_receipt':values['amount_minor']=12001
    if fault=='over_invoice':values['amount_minor']=15001
    if fault=='wrong_receipt':values['receipt_id']=uuid4()
    if fault=='foreign_role':actor=setup_booking[3]
    if fault=='stale_booking':values['expected_booking_version']=1
    if fault=='stale_receipt':values['expected_receipt_version']=2
    from fastapi import HTTPException
    with pytest.raises(HTTPException):await issue_and_apply(db_session,actor,apt.id,BookingReceiptApplyBody(**values),'negative-application')
    assert await db_session.scalar(select(func.count(Invoice.id)))==0
    assert await db_session.scalar(select(func.count(BookingReceiptApplication.id)))==0

@pytest.mark.asyncio
@pytest.mark.parametrize('invoice_total',[100,150])
async def test_definitive_unused_excess_refund_preserves_backed_application_and_exact_balance(db_session,setup_booking,staff_user,monkeypatch,invoice_total):
    apt,order=await prepared(db_session,setup_booking,staff_user,monkeypatch)
    line=await db_session.scalar(select(Labor));line.total_cost=Decimal(invoice_total);line.hourly_rate=Decimal(invoice_total);await db_session.commit()
    import app.services.service_checklist as checklist
    import app.api.v1.endpoints.invoices as invoices
    import app.services.fleet_financial_wakeup as wakeup
    monkeypatch.setattr(checklist,'guard_completion',AsyncMock())
    monkeypatch.setattr(invoices,'enqueue_invoice_created_email',AsyncMock(return_value=False))
    monkeypatch.setattr(invoices,'enqueue_quickbooks_invoice_sync',AsyncMock())
    monkeypatch.setattr(wakeup,'enqueue_financial_wakeup',AsyncMock());monkeypatch.setattr(wakeup,'enqueue_settlement_wakeup',AsyncMock())
    view=await prepayment_view(db_session,apt)
    await issue_and_apply(db_session,staff_user,apt.id,BookingReceiptApplyBody(repair_order_id=order.id,receipt_id=apt.confirmed_receipt_id,expected_booking_version=apt.booking_version,expected_receipt_version=1,amount_minor=10000,expected_invoice_economics_sha256=view['invoice_preview']['invoice_economics_sha256'],accounting_mode='external_manual'),'apply-retain-excess')
    from types import SimpleNamespace
    from app.db.models.booking_payment import BookingReceipt,BookingPaymentAttempt
    from app.api.v1.endpoints.appointments import BookingRefundVerificationBody
    from app.services import booking_payments as booking
    from test_verified_booking_flow import result
    import app.services.booking_refund_verification as verification
    receipt=await db_session.scalar(select(BookingReceipt));attempt=await db_session.scalar(select(BookingPaymentAttempt))
    monkeypatch.setattr(booking.provider,'retrieve_booking_payment',AsyncMock(return_value=result(apt,attempt,provider_id=attempt.provider_intent_id)))
    monkeypatch.setattr(booking.provider,'_connection',AsyncMock(return_value=SimpleNamespace(realm_id='realm-fixture')))
    monkeypatch.setattr(booking.provider,'_healthy_qbo',lambda connection:True)
    monkeypatch.setattr(verification.qbp,'get_refund',AsyncMock(return_value=SimpleNamespace(id='unused-excess',status='SETTLED',amount=Decimal('20'),raw={'id':'unused-excess','status':'SETTLED','amount':'20.00'})))
    response=await verification.verify_existing_refund(db_session,staff_user,apt.id,BookingRefundVerificationBody(refund_id='unused-excess',expected_receipt_version=receipt.version,expected_booking_version=apt.booking_version),'verify-only-unused-excess')
    summary=response['invoice_payment_summary']
    assert summary['state']==('paid' if invoice_total==100 else 'partially_paid')
    assert summary['prepayment_applied_amount']=='100.00' and summary['balance_due']==f'{invoice_total-100:.2f}'
    assert not summary['payment_verification_required']
    from app.services.booking_invoice_guard import require_booking_prepayment_resolved
    await require_booking_prepayment_resolved(db_session,apt.tenant_id,order.id)
    assert await db_session.scalar(select(func.count(Payment.id)))==0
    assert response['accounting']['export_hold'] and response['accounting']['state']=='needs_review'
