"""Booking bookkeeping holds protect exact exports without blocking money facts."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4
import pytest
from fastapi import HTTPException, Response
from sqlalchemy import select
from app.db.models.invoice import Invoice
from app.db.models.provider_outbox import ProviderOutboxEvent
from app.services import quickbooks_shop_activation as admission
from app.services import quickbooks_sync_service as sync
from app.services import quickbooks_accounting_service as provider
from app.services.invoice_settlement_service import SettlementDomainError
from app.api.v1.endpoints import fleet_invoice_exports, fleet_repair_financial_exports
from tests.test_booking_application_accounting import context, ack
from app.services import booking_application_accounting as accounting
from tests.test_quickbooks_sync_worker import _add_sync_context

@pytest.mark.asyncio
async def test_permanent_hold_excludes_only_bookkeeping_not_provider_facts(db_session):
    ctx=await context(db_session)
    tenant,receipt,appointment,owner,invoice,application=ctx
    tasks=await accounting.ensure_manual_accounting_tasks(db_session,receipt=receipt,application=application)
    for task in tasks: await ack(db_session,ctx,task)
    with pytest.raises(SettlementDomainError) as error:
        await admission.require_shop_invoice_admission(db_session,invoice)
    assert error.value.code=='quickbooks_booking_accounting_held'
    # Accounting ACK is never authority to dispatch a duplicate export.
    assert await sync.enqueue_quickbooks_invoice_sync(db_session,invoice=invoice) is None
    assert invoice.quickbooks_sync_status=='manual_review'
    assert invoice.quickbooks_invoice_id is None
    assert invoice.quickbooks_synced_at is None
    # Existing-provider verification/expiry admission deliberately stays separate.
    await admission.require_shop_invoice_admission(db_session,invoice,payment=True)
    assert await db_session.scalar(select(Invoice.id).where(Invoice.id==invoice.id,
        admission.admitted_invoice_predicate(Invoice.tenant_id,Invoice.id)))==invoice.id
    assert await db_session.scalar(select(Invoice.id).where(Invoice.id==invoice.id,
        admission.accounting_invoice_predicate(Invoice.tenant_id,Invoice.id))) is None

@pytest.mark.asyncio
async def test_other_invoice_and_tenant_continue_exporting(db_session):
    ctx=await context(db_session)
    other=await _add_sync_context(db_session)
    # Existing worker fixture returns its original invoice and durable envelope.
    invoice=other[0]
    await admission.require_shop_invoice_admission(db_session,invoice)
    assert await db_session.scalar(select(Invoice.id).where(Invoice.id==invoice.id,
        admission.accounting_invoice_predicate(Invoice.tenant_id,Invoice.id)))==invoice.id
    assert not await accounting.invoice_has_booking_export_hold(db_session,invoice.tenant_id,ctx[-2].id)

@pytest.mark.asyncio
@pytest.mark.parametrize('event_type',['quickbooks.invoice.sync.v1','invoice_payment.accounting_sync','invoice_refund.accounting_sync','customer_credit.accounting_sync'])
async def test_unmanaged_accounting_events_do_not_escape_hold(db_session,event_type):
    tenant,receipt,appointment,owner,invoice,application=await context(db_session)
    event=ProviderOutboxEvent(tenant_id=tenant.id,event_type=event_type,aggregate_type='invoice',aggregate_id=invoice.id,
        idempotency_key=str(uuid4()),payload={'invoice_id':str(invoice.id)})
    assert not await admission.event_admitted(db_session,event)

@pytest.mark.asyncio
async def test_provider_refund_event_is_not_an_accounting_export(db_session):
    tenant,receipt,appointment,owner,invoice,application=await context(db_session)
    from app.services.db048_accounting_reconciliation import PROVIDER_REFUND_EVENT
    event=ProviderOutboxEvent(tenant_id=tenant.id,event_type=PROVIDER_REFUND_EVENT,aggregate_type='invoice',aggregate_id=invoice.id,
        idempotency_key=str(uuid4()),payload={'invoice_id':str(invoice.id)})
    assert await admission.event_admitted(db_session,event)

@pytest.mark.asyncio
@pytest.mark.parametrize('operation',['invoice','payment','refund'])
async def test_provider_bookkeeping_entrypoints_stop_before_external_io(db_session,monkeypatch,operation):
    tenant,receipt,appointment,owner,invoice,application=await context(db_session)
    async def forbidden(*args,**kwargs): raise AssertionError('Provider bookkeeping must not be dispatched')
    monkeypatch.setattr(provider,'_request',forbidden)
    monkeypatch.setattr(provider,'_query',forbidden)
    payment=SimpleNamespace(invoice_payment_attempt_id=None,quickbooks_payment_id=None)
    with pytest.raises(provider.QuickBooksAccountingError,match='managed separately'):
        if operation=='invoice': await provider.sync_invoice(None,invoice,None)
        elif operation=='payment': await provider.sync_payment(None,payment,invoice,None)
        else: await provider.create_refund_receipt(None,payment,invoice,None,refund_id='test-refund',amount=1)

@pytest.mark.asyncio
async def test_incremental_accounting_feed_refuses_held_window(db_session):
    tenant,receipt,appointment,owner,invoice,application=await context(db_session)
    key=SimpleNamespace(id=uuid4(),tenant_id=tenant.id,customer_id=appointment.customer_id)
    now=datetime.now(timezone.utc)
    with pytest.raises(HTTPException) as error:
        await fleet_invoice_exports.list_invoices(Response(),updated_since=now-timedelta(days=1),updated_before=now,
            limit=1,cursor=None,db=db_session,key=key)
    assert error.value.status_code==409
    assert error.value.detail['code']=='booking_accounting_export_held'
    assert not hasattr(key,'last_used_at')

@pytest.mark.asyncio
async def test_complete_financial_snapshot_never_silently_omits_held_invoice(db_session):
    tenant,receipt,appointment,owner,invoice,application=await context(db_session)
    from app.db.models.repair_order import RepairOrder, RepairOrderStatus
    order=await db_session.get(RepairOrder,application.repair_order_id)
    order.status=RepairOrderStatus.COMPLETED
    await db_session.flush()
    key=SimpleNamespace(id=uuid4(),tenant_id=tenant.id,customer_id=appointment.customer_id)
    with pytest.raises(HTTPException) as error:
        await fleet_repair_financial_exports.repair_financial_manifest(SimpleNamespace(query_params={}),Response(),db=db_session,key=key)
    assert error.value.status_code==409
    assert error.value.detail['code']=='booking_accounting_export_held'

@pytest.mark.asyncio
async def test_accounting_pdf_is_held_while_normal_customer_pdf_route_is_unchanged(db_session):
    tenant,receipt,appointment,owner,invoice,application=await context(db_session)
    key=SimpleNamespace(id=uuid4(),tenant_id=tenant.id,customer_id=appointment.customer_id)
    with pytest.raises(HTTPException) as error:
        await fleet_invoice_exports.invoice_pdf(invoice.id,db=db_session,key=key)
    assert error.value.status_code==409
    assert error.value.detail['code']=='booking_accounting_export_held'

@pytest.mark.asyncio
async def test_incremental_hold_after_first_row_blocks_whole_window(db_session):
    tenant,receipt,appointment,owner,held_invoice,application=await context(db_session)
    from app.db.models.repair_order import RepairOrder, RepairOrderStatus
    from app.db.models.invoice import InvoiceStatus
    older=datetime.now(timezone.utc)-timedelta(hours=2)
    from app.db.models.vehicle import Vehicle
    earlier_vehicle=Vehicle(tenant_id=tenant.id,customer_id=appointment.customer_id,make='Demo',model='Earlier truck',
        vin=uuid4().hex[:17],created_at=older,updated_at=older)
    db_session.add(earlier_vehicle);await db_session.flush()
    order=RepairOrder(tenant_id=tenant.id,customer_id=appointment.customer_id,vehicle_id=earlier_vehicle.id,
        order_number='older-'+uuid4().hex,status=RepairOrderStatus.COMPLETED,created_at=older,updated_at=older)
    db_session.add(order);await db_session.flush()
    plain=Invoice(tenant_id=tenant.id,repair_order_id=order.id,billed_customer_id=appointment.customer_id,
        invoice_number='older-'+uuid4().hex,status=InvoiceStatus.SENT,subtotal=1,total_amount=1,tax_amount=0,discount_amount=0,
        created_at=older,updated_at=older)
    db_session.add(plain);await db_session.flush()
    key=SimpleNamespace(id=uuid4(),tenant_id=tenant.id,customer_id=appointment.customer_id)
    effective=fleet_invoice_exports._effective_updated_at()
    first=(await db_session.execute(fleet_invoice_exports._invoice_query(key).order_by(effective,Invoice.id).limit(1))).first()
    assert first[0].id==plain.id  # The held invoice lies beyond the requested first row.
    with pytest.raises(HTTPException) as error:
        await fleet_invoice_exports.list_invoices(Response(),updated_since=older-timedelta(hours=1),
            updated_before=datetime.now(timezone.utc),limit=1,cursor=None,db=db_session,key=key)
    assert error.value.detail['code']=='booking_accounting_export_held'

@pytest.mark.asyncio
async def test_held_head_does_not_starve_an_unrelated_accounting_event(db_session,monkeypatch):
    tenant,receipt,appointment,owner,invoice,application=await context(db_session)
    held=ProviderOutboxEvent(tenant_id=tenant.id,event_type=sync.QUICKBOOKS_INVOICE_SYNC_EVENT,
        aggregate_type='quickbooks_invoice',aggregate_id=invoice.id,payload={'invoice_id':str(invoice.id),'operation':'sync'},
        idempotency_key='held-'+uuid4().hex,status='pending',available_at=sync._now()-timedelta(hours=1))
    db_session.add(held);await db_session.commit()
    other_invoice,other_event=await _add_sync_context(db_session)
    calls=[]
    async def no_refresh(connection): pass
    async def safe_sync(connection,current,customer):
        calls.append(current.id)
        assert current.id==other_invoice.id
        current.quickbooks_invoice_id='fixture-invoice'
        current.quickbooks_sync_status='synced'
        return 'fixture-invoice'
    monkeypatch.setattr(sync,'_refresh_if_needed',no_refresh)
    monkeypatch.setattr(sync,'sync_invoice',safe_sync)
    from sqlalchemy.ext.asyncio import async_sessionmaker
    results=await sync.process_quickbooks_invoice_sync_events(session_factory=async_sessionmaker(db_session.bind,expire_on_commit=False),batch_size=3)
    await db_session.refresh(held);await db_session.refresh(other_event)
    assert calls==[other_invoice.id]
    assert held.status=='pending' and held.attempt_count==0 and held.lock_token is None
    assert other_event.status=='succeeded'
    assert results['succeeded']==1

@pytest.mark.asyncio
@pytest.mark.parametrize('next_kind',['provider_refund','accounting'])
async def test_db048_permanent_held_prefix_does_not_starve_later_work(db_session,monkeypatch,next_kind):
    from app.services import db048_accounting_reconciliation as worker
    from sqlalchemy.ext.asyncio import async_sessionmaker
    tenant,receipt,appointment,owner,invoice,application=await context(db_session)
    prefix=[ProviderOutboxEvent(tenant_id=tenant.id,event_type=worker.PAYMENT_ACCOUNTING_EVENT,
        aggregate_type='invoice',aggregate_id=invoice.id,payload={'invoice_id':str(invoice.id)},
        idempotency_key='held-prefix-'+uuid4().hex,status='pending',available_at=sync._now()-timedelta(hours=1)) for _ in range(2)]
    db_session.add_all(prefix);await db_session.commit()
    other_invoice,_=await _add_sync_context(db_session)
    next_event=ProviderOutboxEvent(tenant_id=other_invoice.tenant_id,
        event_type=worker.PROVIDER_REFUND_EVENT if next_kind=='provider_refund' else worker.PAYMENT_ACCOUNTING_EVENT,
        aggregate_type='payment_refund' if next_kind=='provider_refund' else 'invoice',
        aggregate_id=uuid4() if next_kind=='provider_refund' else other_invoice.id,
        payload={'invoice_id':str(other_invoice.id),**({'refund_id':str(uuid4())} if next_kind=='provider_refund' else {})},
        idempotency_key='next-work-'+uuid4().hex,status='pending',available_at=sync._now()-timedelta(minutes=1))
    db_session.add(next_event);await db_session.commit()
    calls=[]
    async def refund_boundary(db,event):
        calls.append(event.id);assert event.id==next_event.id
        return 'offline-existing-refund-work'
    async def load(db,event):
        assert event.id==next_event.id
        return SimpleNamespace(connection=None,event_id=event.id)
    async def refresh(db,connection): pass
    async def deliver(db,envelope):
        calls.append(envelope.event_id);return 'offline-accounting-work'
    monkeypatch.setattr(worker,'_submit_stripe_refund',refund_boundary)
    monkeypatch.setattr(worker,'load_accounting_envelope',load)
    monkeypatch.setattr(worker,'_refresh_accounting_connection_if_needed',refresh)
    monkeypatch.setattr(worker,'deliver_accounting_envelope',deliver)
    result=await worker.process_due_db048_outbox_events(session_factory=async_sessionmaker(db_session.bind,expire_on_commit=False),batch_size=2)
    assert result['claimed']==1 and result['succeeded']==1
    assert calls==[next_event.id]
    for event in prefix:
        await db_session.refresh(event)
        assert event.status=='pending' and event.attempt_count==0 and event.lock_token is None
    await db_session.refresh(next_event)
    assert next_event.status=='succeeded'
