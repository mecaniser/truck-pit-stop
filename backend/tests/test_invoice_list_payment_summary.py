"""List serialization uses fresh read-only payment facts, not invoice totals/status."""
import json
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import event

from app.api.v1.endpoints.invoices import InvoiceResponse, list_invoices
from app.db.models.customer import Customer
from app.db.models.invoice import Invoice, InvoiceStatus
from app.db.models.invoice_read_model import InvoiceReadModel
from app.db.models.invoice_settlement import InvoiceSettlement
from app.db.models.payment import Payment, PaymentMethod, PaymentStatus
from app.db.models.repair_order import RepairOrder
from app.db.models.tenant import Tenant
from app.db.models.user import UserRole
from app.db.models.vehicle import Vehicle


async def setup_invoice(db, *, projected=False, status='sent', applied=None, pending='0.00', refund='0.00', credit='0.00', reconciliation='native'):
    tenant=Tenant(id=uuid4(), name='Summary fixture shop', slug=f'summary-{uuid4().hex}')
    customer=Customer(id=uuid4(),tenant_id=tenant.id,first_name='Synthetic',last_name='Customer',email=f'{uuid4().hex}@example.invalid')
    vehicle=Vehicle(id=uuid4(),tenant_id=tenant.id,customer_id=customer.id,make='Synthetic',model='Truck')
    order=RepairOrder(id=uuid4(),tenant_id=tenant.id,customer_id=customer.id,vehicle_id=vehicle.id,order_number=f'RO-{uuid4().hex}')
    inv=Invoice(id=uuid4(),tenant_id=tenant.id,repair_order_id=order.id,invoice_number=f'INV-{uuid4().hex}',status=InvoiceStatus(status),subtotal=Decimal('100.00'),total_amount=Decimal('100.00'),tax_amount=0,discount_amount=0)
    db.add_all([tenant,customer,vehicle,order,inv]);await db.flush()
    if applied is not None:
        db.add(InvoiceSettlement(id=uuid4(),tenant_id=tenant.id,invoice_id=inv.id,customer_id=customer.id,principal_total=100,confirmed_principal=Decimal(applied),active_pending_principal=Decimal(pending),refund_pending=Decimal(refund),unapplied_credit=Decimal(credit),state='unpaid',legacy_reconciliation_status=reconciliation))
    if projected:
        payload=InvoiceResponse.model_validate(inv).model_dump(mode='json')
        # Persisted display payload can be stale: financial projection must not use it.
        payload['total_amount']='999.00';payload['status']='paid'
        payload['payment_summary']={'state':'paid','balance_due':'0.00','basis':'stale_projection'}
        db.add(InvoiceReadModel(invoice_id=inv.id,tenant_id=tenant.id,repair_order_id=order.id,customer_id=customer.id,status=status,created_at=inv.created_at,payload=payload))
    await db.commit()
    actor=SimpleNamespace(id=uuid4(),tenant_id=tenant.id,customer_id=customer.id,role=UserRole.CUSTOMER)
    return actor,inv,customer


async def listed(db,actor):
    response=await list_invoices(status_filter=None,repair_order_id=None,skip=0,limit=100,paginated=True,db=db,current_user=actor)
    return json.loads(response.body)


@pytest.mark.asyncio
@pytest.mark.parametrize('projected',[False,True])
@pytest.mark.parametrize('status,applied,pending,refund,credit,reconciliation,state,balance',[
    ('sent','0.00','0.00','0.00','0.00','native','unpaid','100.00'),
    ('sent','40.00','0.00','0.00','0.00','native','partially_paid','60.00'),
    ('sent','0.00','20.00','0.00','0.00','native','payment_pending','100.00'),
    ('paid','40.00','20.00','0.00','0.00','native','partially_paid_pending','60.00'),
    ('paid','100.00','0.00','20.00','15.00','native','paid','0.00'),
    ('paid','100.00','0.00','0.00','0.00','legacy_paid_without_tender','paid','0.00'),
    ('sent','40.00','0.00','0.00','0.00','needs_review','unknown',None),
    ('cancelled','0.00','0.00','0.00','0.00','native','cancelled',None),
])
async def test_list_serializes_fresh_remaining_payment_facts(db_session,projected,status,applied,pending,refund,credit,reconciliation,state,balance):
    actor,inv,_=await setup_invoice(db_session,projected=projected,status=status,applied=applied,pending=pending,refund=refund,credit=credit,reconciliation=reconciliation)
    before=(inv.status,inv.total_amount,inv.updated_at)
    payload=await listed(db_session,actor)
    summary=payload['items'][0]['payment_summary']
    assert (summary['state'],summary['balance_due'])==(state,balance)
    if refund!='0.00':assert 'refund is pending' in summary['note'] and 'Unapplied funds' in summary['note']
    if reconciliation=='legacy_paid_without_tender':assert summary['applied_amount'] is None
    assert before==(inv.status,inv.total_amount,inv.updated_at)
    assert not db_session.new and not db_session.dirty and not db_session.deleted


@pytest.mark.asyncio
@pytest.mark.parametrize('projected',[False,True])
async def test_legacy_payment_and_foreign_evidence_are_scoped(db_session,projected):
    actor,inv,customer=await setup_invoice(db_session,projected=projected)
    other=Tenant(id=uuid4(),name='Other shop',slug=f'other-{uuid4().hex}')
    db_session.add(other);await db_session.flush()
    for tenant_id,amount in [(actor.tenant_id,'40.00'),(other.id,'999.00')]:
        db_session.add(Payment(id=uuid4(),tenant_id=tenant_id,invoice_id=inv.id,payment_number=f'PAY-{uuid4().hex}',amount=Decimal(amount),method=PaymentMethod.CHECK,status=PaymentStatus.COMPLETED))
    await db_session.commit()
    own=await listed(db_session,actor)
    assert own['items'][0]['payment_summary']['balance_due']=='60.00'
    actor.customer_id=uuid4()
    assert (await listed(db_session,actor))['items']==[]
    actor.customer_id=customer.id;actor.tenant_id=other.id
    assert (await listed(db_session,actor))['items']==[]
    actor.tenant_id=inv.tenant_id;actor.customer_id=None
    assert (await listed(db_session,actor))['items']==[]


@pytest.mark.asyncio
@pytest.mark.parametrize('projected',[False,True])
async def test_summary_refetch_reads_new_confirmed_and_pending_without_write(db_session,projected):
    actor,inv,_=await setup_invoice(db_session,projected=projected,applied='40.00')
    assert (await listed(db_session,actor))['items'][0]['payment_summary']['balance_due']=='60.00'
    from sqlalchemy import select
    s=(await db_session.execute(select(InvoiceSettlement).where(InvoiceSettlement.invoice_id==inv.id))).scalar_one()
    s.confirmed_principal=Decimal('60.00');s.active_pending_principal=Decimal('10.00');await db_session.commit()
    summary=(await listed(db_session,actor))['items'][0]['payment_summary']
    assert summary['balance_due']=='40.00' and summary['pending_amount']=='10.00'
    assert not db_session.new and not db_session.dirty


@pytest.mark.asyncio
@pytest.mark.parametrize('projected',[False,True])
@pytest.mark.parametrize('count',[1,50,100])
async def test_payment_evidence_query_count_is_bounded_for_page(db_session,projected,count):
    actor,first,customer=await setup_invoice(db_session,projected=projected)
    original_order=await db_session.get(RepairOrder,first.repair_order_id)
    for _ in range(count-1):
        order=RepairOrder(id=uuid4(),tenant_id=actor.tenant_id,customer_id=customer.id,vehicle_id=original_order.vehicle_id,order_number=f'RO-{uuid4().hex}')
        inv=Invoice(id=uuid4(),tenant_id=actor.tenant_id,repair_order_id=order.id,invoice_number=f'INV-{uuid4().hex}',status=InvoiceStatus.SENT,subtotal=100,total_amount=100,tax_amount=0,discount_amount=0)
        db_session.add_all([order,inv]);await db_session.flush()
        if projected:
            db_session.add(InvoiceReadModel(invoice_id=inv.id,tenant_id=inv.tenant_id,repair_order_id=order.id,customer_id=customer.id,status='sent',created_at=inv.created_at,payload=InvoiceResponse.model_validate(inv).model_dump(mode='json')))
    await db_session.commit()
    statements=[]
    engine=db_session.bind.sync_engine
    def capture(_conn,_cursor,statement,*_args):statements.append(statement)
    event.listen(engine,'before_cursor_execute',capture)
    try:payload=await listed(db_session,actor)
    finally:event.remove(engine,'before_cursor_execute',capture)
    assert len(payload['items'])==count
    assert sum('FROM invoice_settlements' in s for s in statements)==1
    assert sum('FROM payments' in s for s in statements)==1
    # Existing charge-adjustment selectin loading remains page-batched too.
    assert len(statements)==(5 if projected else 6)
    assert all(s.lstrip().upper().startswith('SELECT') for s in statements)


@pytest.mark.asyncio
async def test_empty_result_does_not_load_payment_evidence(db_session):
    actor,_,_=await setup_invoice(db_session)
    actor.customer_id=uuid4()
    statements=[];engine=db_session.bind.sync_engine
    def capture(_conn,_cursor,statement,*_args):statements.append(statement)
    event.listen(engine,'before_cursor_execute',capture)
    try:assert (await listed(db_session,actor))['items']==[]
    finally:event.remove(engine,'before_cursor_execute',capture)
    assert not any('FROM invoice_settlements' in s or 'FROM payments' in s for s in statements)


@pytest.mark.asyncio
@pytest.mark.parametrize('projected',[False,True])
async def test_foreign_settlement_cannot_override_current_tenant_legacy_payment(db_session,projected):
    actor,inv,customer=await setup_invoice(db_session,projected=projected)
    foreign=Tenant(id=uuid4(),name='Foreign',slug=f'foreign-{uuid4().hex}')
    db_session.add(foreign);await db_session.flush()
    db_session.add_all([
        InvoiceSettlement(id=uuid4(),tenant_id=foreign.id,invoice_id=inv.id,customer_id=customer.id,principal_total=100,confirmed_principal=100),
        Payment(id=uuid4(),tenant_id=actor.tenant_id,invoice_id=inv.id,payment_number=f'PAY-{uuid4().hex}',amount=40,method=PaymentMethod.CHECK,status=PaymentStatus.COMPLETED),
    ])
    await db_session.commit()
    summary=(await listed(db_session,actor))['items'][0]['payment_summary']
    assert summary['basis']=='legacy_payments' and summary['balance_due']=='60.00'


@pytest.mark.asyncio
@pytest.mark.parametrize('projected',[False,True])
async def test_cash_receipt_precedence_uses_current_invoice_not_stale_payload(db_session,projected):
    actor,inv,_=await setup_invoice(db_session,projected=projected,status='paid',applied='100.00',reconciliation='needs_review')
    db_session.add(Payment(id=uuid4(),tenant_id=actor.tenant_id,invoice_id=inv.id,payment_number=f'PAY-{uuid4().hex}',amount=100,method=PaymentMethod.CASH,status=PaymentStatus.COMPLETED))
    await db_session.commit()
    item=(await listed(db_session,actor))['items'][0]
    assert item['payment_summary']['basis']=='cash_receipt'
    assert item['payment_summary']['balance_due']=='0.00'
    assert item['payment_summary']['applied_amount']=='100.00'
    assert Decimal(str(item['cash_receipt']['amount']))==Decimal('100.00')


@pytest.mark.asyncio
async def test_failed_financial_read_propagates_instead_of_fabricating_balance(db_session,monkeypatch):
    from app.services.invoice_payment_presentation import load_payment_summaries
    actor,inv,_=await setup_invoice(db_session)
    async def unavailable(*_args,**_kwargs):raise RuntimeError('Synthetic evidence read failure')
    monkeypatch.setattr(db_session,'execute',unavailable)
    with pytest.raises(RuntimeError,match='Synthetic evidence read failure'):
        await load_payment_summaries(db_session,[inv],tenant_id=actor.tenant_id)


@pytest.mark.asyncio
async def test_detail_response_keeps_existing_payment_summary_after_base_field_addition(db_session):
    from app.api.v1.endpoints.invoices import get_invoice
    actor,inv,_=await setup_invoice(db_session,applied='40.00',pending='20.00')
    detail=await get_invoice(inv.id,db=db_session,current_user=actor)
    assert detail.payment_summary.balance_due=='60.00'
    assert detail.payment_summary.pending_amount=='20.00'
    assert detail.model_dump(mode='json')['payment_summary']['state']=='partially_paid_pending'


@pytest.mark.asyncio
async def test_stale_or_invalid_cached_summary_is_not_validated_as_current_evidence(db_session):
    from sqlalchemy import select
    actor,inv,_=await setup_invoice(db_session,projected=True,applied='40.00')
    row=(await db_session.execute(select(InvoiceReadModel).where(InvoiceReadModel.invoice_id==inv.id))).scalar_one()
    row.payload={**row.payload,'payment_summary':'invalid old cached evidence'}
    await db_session.commit()
    assert (await listed(db_session,actor))['items'][0]['payment_summary']['balance_due']=='60.00'


@pytest.mark.asyncio
@pytest.mark.parametrize('projected',[False,True])
@pytest.mark.parametrize('completed,pending,refund,state,balance',[
    ('0.00','20.00',False,'payment_pending','100.00'),
    ('40.00','20.00',False,'partially_paid_pending','60.00'),
    ('40.00','0.00',True,'unknown',None),
])
async def test_legacy_list_keeps_pending_and_refund_semantics(db_session,projected,completed,pending,refund,state,balance):
    actor,inv,_=await setup_invoice(db_session,projected=projected)
    for amount,status in [(completed,PaymentStatus.COMPLETED),(pending,PaymentStatus.PENDING)]:
        if Decimal(amount)==0:continue
        db_session.add(Payment(id=uuid4(),tenant_id=actor.tenant_id,invoice_id=inv.id,payment_number=f'PAY-{uuid4().hex}',amount=Decimal(amount),method=PaymentMethod.CHECK,status=status,quickbooks_refunded_amount=Decimal('5.00') if refund else None))
    await db_session.commit()
    summary=(await listed(db_session,actor))['items'][0]['payment_summary']
    assert (summary['state'],summary['balance_due'])==(state,balance)
    if Decimal(pending)>0:assert summary['pending_amount']==pending


@pytest.mark.asyncio
async def test_deleted_payment_and_deleted_settlement_are_not_current_evidence(db_session):
    from datetime import datetime,timezone
    actor,inv,customer=await setup_invoice(db_session)
    now=datetime.now(timezone.utc)
    db_session.add_all([
        InvoiceSettlement(id=uuid4(),tenant_id=actor.tenant_id,invoice_id=inv.id,customer_id=customer.id,principal_total=100,confirmed_principal=100,deleted_at=now),
        Payment(id=uuid4(),tenant_id=actor.tenant_id,invoice_id=inv.id,payment_number=f'PAY-{uuid4().hex}',amount=100,method=PaymentMethod.CHECK,status=PaymentStatus.COMPLETED,deleted_at=now),
    ])
    await db_session.commit()
    summary=(await listed(db_session,actor))['items'][0]['payment_summary']
    assert summary['state']=='unpaid' and summary['balance_due']=='100.00'


@pytest.mark.asyncio
@pytest.mark.parametrize('selected_tenant',[None,'different'])
async def test_batch_loader_rejects_unscoped_invoice_inputs_before_any_read(selected_tenant):
    from app.services.invoice_payment_presentation import load_payment_summaries
    tenant_id=uuid4()
    inv=SimpleNamespace(id=uuid4(),tenant_id=tenant_id)
    class NoRead:
        async def execute(self,*_args,**_kwargs):raise AssertionError('No evidence read is permitted')
    with pytest.raises(ValueError,match='selected tenant'):
        await load_payment_summaries(NoRead(),[inv],tenant_id=None if selected_tenant is None else uuid4())


@pytest.mark.asyncio
async def test_empty_batch_does_not_read_evidence():
    from app.services.invoice_payment_presentation import load_payment_summaries
    class NoRead:
        async def execute(self,*_args,**_kwargs):raise AssertionError('No evidence read is permitted')
    assert await load_payment_summaries(NoRead(),[],tenant_id=uuid4())=={}


@pytest.mark.asyncio
@pytest.mark.parametrize('projected', [False, True])
@pytest.mark.parametrize('prefix,source_number', [('TPS', '001687'), ('DEL', '1687')])
async def test_list_keeps_reviewed_tenant_alias_and_legal_identity(db_session, monkeypatch, projected, prefix, source_number):
    """Real handoff authorization survives both list paths and fresh summaries."""
    from datetime import datetime, timedelta, timezone
    from test_db149_source_collection import context
    from app.schemas.source_debt_handoff import BillToReview, SourceVersionRequest
    from app.services import source_debt_handoff as svc

    tenant, owner, source, original, proof, body = await context(db_session, monkeypatch)
    tenant.order_number_prefix = prefix
    original.source = 'easy_truck_shop_import'
    source.company_name = 'Original Reviewed Legal Business'
    target = Customer(id=uuid4(), tenant_id=tenant.id, first_name='Portal', last_name='Customer',
                      company_name='Portal Account (DBN)', email=f'{uuid4().hex}@example.invalid')
    db_session.add(target)
    await db_session.flush()
    proof.update(source_customer=source, customer=target)
    proof['latest']['invoice_number'] = source_number
    body = body.model_copy(update={'target_customer_id': target.id})
    body.bill_to_review = BillToReview(
        mode='owner_same_legal_entity', source_customer_id=source.id, target_customer_id=target.id,
        attested_same_legal_entity=True, confirmation_reference='Synthetic exact invoice owner review',
        reason='Same legal business, existing portal account',
    )
    handoff = await svc.prepare(db_session, tenant.id, owner, body, 'list-identity-prepare')
    proof['summary'].observed_at = datetime.now(timezone.utc) + timedelta(seconds=1)
    handoff, _ = await svc.activate(db_session, handoff, owner, SourceVersionRequest(
        expected_version=1, expected_source_capture_sha256='a'*64, expected_source_revision='b'*64,
    ), 'list-identity-activate')
    native = await db_session.get(Invoice, handoff.native_invoice_id)
    canonical = native.invoice_number
    authorization = dict(handoff.bill_to_authorization)
    authorization_hash = handoff.bill_to_authorization_sha256
    if projected:
        payload = InvoiceResponse.model_validate(native).model_dump(mode='json')
        payload['source_collection'] = {'display_invoice_number': 'STALE', 'customer_display_company': 'Stale name'}
        payload['payment_summary'] = {'state': 'paid', 'balance_due': '0.00', 'basis': 'stale_projection'}
        db_session.add(InvoiceReadModel(invoice_id=native.id, tenant_id=tenant.id,
            repair_order_id=native.repair_order_id, customer_id=target.id, status=native.status.value,
            created_at=native.created_at, payload=payload))
    await db_session.commit()
    actor = SimpleNamespace(id=uuid4(), tenant_id=tenant.id, customer_id=target.id, role=UserRole.CUSTOMER)
    items = (await listed(db_session, actor))['items']
    assert len(items) == 1
    item = items[0]
    assert item['id'] == str(native.id) and item['invoice_number'] == canonical
    assert item['source_collection']['display_invoice_number'] == f'{prefix}-{source_number}'
    assert item['source_collection']['customer_display_company'] == 'Original Reviewed Legal Business'
    assert item['payment_summary']['balance_due'] == '600.00'
    assert handoff.bill_to_authorization == authorization
    assert handoff.bill_to_authorization['original_bill_to_name'] == 'Original Reviewed Legal Business'
    assert handoff.bill_to_authorization_sha256 == authorization_hash
    assert target.company_name == 'Portal Account (DBN)'
    assert not db_session.new and not db_session.dirty and not db_session.deleted
