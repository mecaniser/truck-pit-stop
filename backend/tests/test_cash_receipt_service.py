from datetime import datetime, timezone
from decimal import Decimal as D
from types import SimpleNamespace as NS
from uuid import uuid4
import pytest
from app.services.cash_receipt_service import project_cash_receipt, receipt_invoice_view


def evidence():
    inv = NS(id=uuid4(), tenant_id=uuid4(), status='paid', subtotal=D('371.72'),
             shop_supplies_amount=D('4.50'), discount_amount=D('0'), tax_amount=D('0'),
             service_fee_amount=D('11.25'), total_amount=D('387.47'), paid_at=datetime.now(timezone.utc))
    pay = NS(id=uuid4(), invoice_id=inv.id, tenant_id=inv.tenant_id, method='cash',
             status='completed', amount=D('376.22'), created_at=inv.paid_at, invoice_payment_attempt_id=None)
    return inv, pay


def test_legacy_cash_reconciles_without_mutating_invoice():
    inv, pay = evidence()
    receipt = project_cash_receipt(inv, [pay])
    assert receipt.amount == D('376.22')
    assert receipt.tax_amount == receipt.service_fee_amount == 0
    assert receipt_invoice_view(inv, receipt).total_amount == D('376.22')
    assert inv.total_amount == D('387.47')


@pytest.mark.parametrize('field,change', [('amount',D('376.21')),('method','check'),('status','refunded'),('tenant_id',uuid4()),('deleted_at',datetime.now(timezone.utc))])
def test_rejects_ambiguous_or_foreign_evidence(field, change):
    inv, pay = evidence()
    setattr(pay, field, change)
    assert project_cash_receipt(inv, [pay]) is None


def test_rejects_mixed_or_missing_payments():
    inv, pay = evidence()
    assert project_cash_receipt(inv, []) is None
    assert project_cash_receipt(inv, [pay,pay]) is None


def test_native_tax_is_retained_and_fee_tax_removed():
    inv,pay=evidence()
    inv.tax_amount=D('30.99');pay.amount=D('406.22')
    settlement=NS(id=uuid4(),tenant_id=inv.tenant_id,invoice_id=inv.id,state='paid',
                  confirmed_principal=pay.amount,principal_total=pay.amount,max_card_fee_tax=D('.99'),
                  active_pending_principal=0,unapplied_credit=0,refund_pending=0)
    attempt=NS(id=uuid4(),payment_id=pay.id,tenant_id=inv.tenant_id,invoice_id=inv.id,
               settlement_id=settlement.id,state='confirmed',rail='cash',received_amount=pay.amount,
               applied_principal_amount=pay.amount,card_fee_amount=0,card_fee_tax_amount=0,
               applied_card_fee_amount=0,applied_card_fee_tax_amount=0,unapplied_amount=0,confirmed_at=inv.paid_at)
    pay.invoice_payment_attempt_id=attempt.id
    assert project_cash_receipt(inv,[pay],settlement,[attempt]).tax_amount == D('30')
    settlement.refund_pending=D('1')
    assert project_cash_receipt(inv,[pay],settlement,[attempt]) is None


def test_pdf_uses_explicit_cash_labels(monkeypatch):
    from app.services.pdf_service import generate_invoice_pdf
    from app.services import pdf_service
    labels=[]
    original=pdf_service._p
    def capture(text, *args, **kwargs):
        labels.append(text)
        return original(text,*args,**kwargs)
    monkeypatch.setattr(pdf_service, "_p", capture)
    pdf=generate_invoice_pdf(invoice_number='TEST',order_number='RO',invoice_date='09/12/2026',
        status='paid',customer_name='Test',shop_name='Shop',cash_receipt=True,
        subtotal=D('100'),total_amount=D('100'), service_completed=None,due_date=None,customer_company=None,customer_email=None,customer_phone=None,shop_address=None,shop_email=None,shop_phone=None,vehicle_year=None,vehicle_make='',vehicle_model='')
    assert pdf.startswith(b'%PDF')
    text=' '.join(labels)
    assert 'TOTAL PAID' in text
    assert 'Sales tax (not charged)' in text
    assert 'Processing Fee' in text
    assert 'TOTAL DUE' not in text


@pytest.mark.asyncio
async def test_confirmation_email_and_attachment_use_cash_evidence(monkeypatch):
    from unittest.mock import AsyncMock
    from app.services import invoice_notification_service as service
    inv,pay=evidence()
    inv.invoice_number='TEST-CASH';inv.created_at=inv.paid_at;inv.due_date=None;inv.notes=None
    receipt=project_cash_receipt(inv,[pay])
    monkeypatch.setattr(service,'load_cash_receipt',AsyncMock(return_value=receipt))
    monkeypatch.setattr(service,'generate_invoice_access_link',AsyncMock(return_value='https://example.test/invoice'))
    monkeypatch.setattr(service,'_load_line_items',AsyncMock(return_value=([],[])))
    sender=AsyncMock();monkeypatch.setattr(service,'send_email',sender)
    captured={}
    def pdf(**kwargs):
        captured.update(kwargs)
        return b'%PDF-test'
    monkeypatch.setattr(service,'generate_invoice_pdf',pdf)
    await service.send_invoice_payment_confirmation_email(AsyncMock(),inv,
        NS(id=uuid4(),order_number='RO',work_completed_at=None),
        NS(email='test@example.test',first_name='Test',last_name='Customer',phone=None),None,None)
    body=sender.call_args.kwargs['body']
    assert '$376.22' in body and '$387.47' not in body and '$11.25' not in body
    assert 'Sales tax (not charged)' in body
    assert captured['total_amount'] == D('376.22')
    assert captured['service_fee_amount'] == 0 and captured['tax_amount'] == 0
    assert inv.total_amount == D('387.47')
