from decimal import Decimal
from types import SimpleNamespace as Obj
from uuid import uuid4
import pytest
from app.services.invoice_payment_presentation import project_payment_summary, load_payment_summary, payment_summary_html


def fixtures(status='sent'):
    invoice=Obj(id=uuid4(),tenant_id=uuid4(),status=status,total_amount=Decimal('1000'),pending_zelle_confirmation=False)
    settlement=Obj(invoice_id=invoice.id,tenant_id=invoice.tenant_id,principal_total=Decimal('1000'),confirmed_principal=0,active_pending_principal=0,max_card_fee=0,max_card_fee_tax=0,refund_pending=0,unapplied_credit=0,currency='USD',legacy_reconciliation_status='native',deleted_at=None)
    return invoice,settlement

@pytest.mark.parametrize('applied,pending,status,state,balance',[(0,0,'sent','unpaid','1000.00'),(400,0,'sent','partially_paid','600.00'),(1000,0,'paid','paid','0.00'),(0,400,'sent','payment_pending','1000.00'),(400,200,'sent','partially_paid_pending','600.00'),(0,0,'overdue','overdue','1000.00')])
def test_native_versions_share_authoritative_balance(applied,pending,status,state,balance):
    invoice,settlement=fixtures(status)
    settlement.confirmed_principal=applied
    settlement.active_pending_principal=pending
    summary=project_payment_summary(invoice,settlement)
    assert summary.state==state
    assert summary.balance_due==balance
    assert summary.applied_amount==f'{applied:.2f}'
    if pending:
        assert 'has not reduced' in summary.note
        assert 'Awaiting confirmation' in payment_summary_html(summary)

@pytest.mark.parametrize('field,value',[('tenant_id',uuid4()),('invoice_id',uuid4()),('currency','EUR'),('legacy_reconciliation_status','needs_review'),('principal_total','NaN'),('confirmed_principal',-1)])
def test_bad_or_cross_tenant_projection_preserves_unknown(field,value):
    invoice,settlement=fixtures()
    setattr(settlement,field,value)
    summary=project_payment_summary(invoice,settlement)
    assert summary.state=='unknown'
    assert summary.balance_due is None


def payment(invoice,**overrides):
    data=dict(invoice_id=invoice.id,tenant_id=invoice.tenant_id,status='completed',amount=400,quickbooks_refunded_amount=None,invoice_payment_attempt_id=None,deleted_at=None)
    return Obj(**(data|overrides))


def test_legacy_partial_pending_and_refunded():
    invoice,_=fixtures()
    summary=project_payment_summary(invoice,payments=[payment(invoice),payment(invoice,status='pending',amount=200)])
    assert (summary.state,summary.balance_due,summary.pending_amount)==('partially_paid_pending','600.00','200.00')
    for p in [payment(invoice,status='refunded'),payment(invoice,quickbooks_refunded_amount=50),payment(invoice,tenant_id=uuid4()),payment(invoice,invoice_payment_attempt_id=uuid4())]:
        assert project_payment_summary(invoice,payments=[p]).balance_due is None


def test_paid_status_does_not_invent_amount_received_and_cancelled_never_requests_payment():
    invoice,_=fixtures('paid')
    summary=project_payment_summary(invoice)
    assert summary.balance_due=='0.00'
    assert summary.applied_amount is None
    invoice.status='cancelled'
    summary=project_payment_summary(invoice)
    assert summary.state=='cancelled' and summary.balance_due is None
    assert 'No payment requested' in summary.note


def test_cash_exact_and_baseline_credit_language():
    invoice,settlement=fixtures('paid')
    cash=project_payment_summary(invoice,cash_receipt=Obj(amount=Decimal('252.70')))
    assert (cash.basis,cash.applied_amount,cash.balance_due)==('cash_receipt','252.70','0.00')
    assert 'Cash received' in payment_summary_html(cash)
    settlement.confirmed_principal=1000
    settlement.legacy_reconciliation_status='legacy_paid_snapshot'
    assert project_payment_summary(invoice,settlement).applied_amount is None
    settlement.legacy_reconciliation_status='native'
    summary=project_payment_summary(invoice,settlement)
    assert 'Payments / credits applied' in payment_summary_html(summary)
    assert 'Amount paid' not in payment_summary_html(summary)


def test_refund_and_unapplied_notes_dont_silently_change_principal():
    invoice,s=fixtures('paid');s.confirmed_principal=1000;s.refund_pending=100;s.unapplied_credit=100
    summary=project_payment_summary(invoice,s)
    assert summary.balance_due=='0.00'
    assert 'refund is pending' in summary.note
    assert 'Unapplied funds' in summary.note

@pytest.mark.asyncio
async def test_database_loader_is_read_only_and_tenant_scoped(db_session):
    from app.db.models.tenant import Tenant
    from app.db.models.customer import Customer
    from app.db.models.vehicle import Vehicle
    from app.db.models.repair_order import RepairOrder
    from app.db.models.invoice import Invoice,InvoiceStatus
    from app.db.models.payment import Payment,PaymentMethod,PaymentStatus
    t=Tenant(name='Summary shop',slug='summary-shop')
    c=Customer(tenant=t,first_name='Fixture',last_name='Customer',email='fixture@example.com')
    v=Vehicle(tenant=t,customer=c,make='Demo',model='Truck',vin='1HGBH41JXMN109186')
    order=RepairOrder(tenant=t,customer=c,vehicle=v,order_number='SUMMARY-RO')
    inv=Invoice(tenant=t,repair_order=order,invoice_number='SUMMARY-INV',status=InvoiceStatus.SENT,subtotal=1000,total_amount=1000,tax_amount=0,discount_amount=0)
    db_session.add(inv);await db_session.flush()
    p=Payment(tenant=t,invoice=inv,payment_number='SUMMARY-PAY',amount=400,method=PaymentMethod.CHECK,status=PaymentStatus.COMPLETED)
    db_session.add(p);await db_session.commit()
    before=(inv.status,inv.total_amount,inv.updated_at)
    summary=await load_payment_summary(db_session,inv)
    assert summary.state=='partially_paid' and summary.balance_due=='600.00'
    assert not db_session.new and not db_session.dirty and not db_session.deleted
    assert before==(inv.status,inv.total_amount,inv.updated_at)


@pytest.mark.parametrize('reconciliation,applied', [('native','1000.00'),('reconciled','1000.00'),('legacy_paid_snapshot',None),('legacy_paid_without_tender',None)])
def test_real_reconciliation_vocabulary(reconciliation,applied):
    invoice,s=fixtures('paid');s.confirmed_principal=1000;s.legacy_reconciliation_status=reconciliation
    summary=project_payment_summary(invoice,s)
    assert summary.state=='paid' and summary.balance_due=='0.00'
    assert summary.applied_amount==applied


def test_cash_receipt_all_pdf_generators_use_same_totals(monkeypatch):
    from datetime import datetime,timezone
    from app.api.v1.endpoints import invoices, fleet_invoice_exports as exports
    from app.db.models.invoice import InvoiceStatus
    from app.services.cash_receipt_service import CashReceipt
    from test_invoice_review_link import entities
    tenant,invoice,order,customer=entities()
    invoice.status=InvoiceStatus.PAID;invoice.ets_invoiced_at=None
    invoice.total_amount=Decimal('115');invoice.subtotal=Decimal('100');invoice.shop_supplies_amount=Decimal('3');invoice.tax_amount=Decimal('8');invoice.service_fee_amount=Decimal('4');invoice.discount_amount=Decimal('2')
    order.mileage_in=None
    vehicle=Obj(year=2020,make='Demo',model='Truck',unit_number='DEMO',vin=None,odometer=None)
    receipt=CashReceipt(amount=Decimal('101'),subtotal=Decimal('100'),shop_supplies_amount=Decimal('3'),tax_amount=Decimal('0'),discount_amount=Decimal('2'),paid_at=datetime.now(timezone.utc))
    summary=project_payment_summary(invoice,cash_receipt=receipt)
    captures=[]
    def capture(**kwargs):
        captures.append(kwargs);return b'fixture'
    monkeypatch.setattr(invoices,'generate_invoice_pdf',capture)
    monkeypatch.setattr(exports,'generate_invoice_pdf',capture)
    invoices._build_invoice_pdf_bytes(invoice,order,customer,vehicle,tenant,[],[],None,cash_receipt=receipt,payment_summary=summary)
    exports._integration_pdf(invoice,order,customer,vehicle,tenant,[],[],summary,receipt)
    for field in ('total_amount','tax_amount','service_fee_amount','discount_amount','cash_receipt','payment_summary'):
        assert captures[0][field]==captures[1][field]
    assert captures[0]['total_amount']==Decimal('101')
