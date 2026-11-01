from datetime import datetime,timedelta,timezone
from decimal import Decimal
from types import SimpleNamespace as NS
from uuid import uuid4
from unittest.mock import AsyncMock
import pytest
from sqlalchemy import select,func
from app.services import source_debt_handoff as svc
from app.schemas.source_debt_handoff import PrepareRequest,SourceVersionRequest,ReconcileRequest
from app.db.models.invoice import Invoice
from app.db.models.source_debt_handoff import SourceDebtHandoff,SourceDebtEvent
from app.services.invoice_settlement_service import SettlementDomainError
from test_db048_invoice_settlements import _financial_context

async def context(db,monkeypatch):
    tenant,owner,customer,invoice=await _financial_context(db,monkeypatch,principal=Decimal('1000'),fee=Decimal('0'))
    now=datetime.now(timezone.utc)
    latest={'service_internal_id':'506423','invoice_id':'468019','invoice_number':'1687','service_id':'1821','payment_lines':[]}
    proof=dict(invoice=invoice,order=invoice.repair_order,customer=customer,latest=latest,envelope={'observations':[{'evidence':latest}]},digest='a'*64,revision='b'*64,allocations={},shop='shop',summary=NS(total_amount=Decimal('1000'),recorded_completed_amount=Decimal('400'),recorded_remaining_amount=Decimal('600'),observed_at=now))
    monkeypatch.setattr(svc,'source_proof',AsyncMock(return_value=proof))
    body=PrepareRequest(source_invoice_id=invoice.id,target_customer_id=customer.id,expected_source_capture_sha256='a'*64,expected_source_revision='b'*64,acknowledge_dbn_primary=True)
    return tenant,owner,customer,invoice,proof,body

@pytest.mark.asyncio
async def test_prepare_only_replay_and_activation_requires_post_ack(db_session,monkeypatch):
    t,a,c,original,p,b=await context(db_session,monkeypatch)
    row=await svc.prepare(db_session,t.id,a,b,'prepare')
    assert row.native_invoice_id is None
    assert await svc.prepare(db_session,t.id,a,b,'prepare') is row
    assert await db_session.scalar(select(func.count()).select_from(Invoice))==1
    activate=SourceVersionRequest(expected_version=1,expected_source_capture_sha256='a'*64,expected_source_revision='b'*64)
    with pytest.raises(SettlementDomainError,match='Refresh source evidence'):
        await svc.activate(db_session,row,a,activate,'activate')
    p['summary'].observed_at=datetime.now(timezone.utc)+timedelta(seconds=1)
    row,replay=await svc.activate(db_session,row,a,activate,'activate')
    assert not replay and row.state=='active'
    native=await db_session.get(Invoice,row.native_invoice_id)
    assert native.total_amount==Decimal('600') and native.tax_amount==0
    assert native.repair_order_id==original.repair_order_id
    assert Decimal(native.line_items_snapshot['labor'][0]['total_cost'])==Decimal('600')
    assert original.total_amount==Decimal('1000')
    assert (await svc.activate(db_session,row,a,activate,'activate'))[1]
    with pytest.raises(SettlementDomainError) as exc:
        await svc.get_handoff(db_session,uuid4(),row.id)
    assert exc.value.status_code==404

@pytest.mark.asyncio
async def test_committed_conflict_replays_same_result_and_hash(db_session,monkeypatch):
    t,a,c,original,p,b=await context(db_session,monkeypatch)
    row=await svc.prepare(db_session,t.id,a,b,'prepare')
    p['summary'].observed_at=datetime.now(timezone.utc)+timedelta(seconds=1)
    row,_=await svc.activate(db_session,row,a,SourceVersionRequest(expected_version=1,expected_source_capture_sha256='a'*64,expected_source_revision='b'*64),'activate')
    p['summary'].total_amount=Decimal('999')
    request=ReconcileRequest(expected_version=row.version,source_capture_sha256='a'*64,expected_source_revision='b'*64)
    _,first=await svc.reconcile(db_session,row,a,request,'reconcile')
    await db_session.commit()
    _,second=await svc.reconcile(db_session,row,a,request,'reconcile')
    assert first==second=={'conflict':'source_invoice_total_changed'}
    event=await db_session.scalar(select(SourceDebtEvent).where(SourceDebtEvent.request_key=='reconcile:reconcile'))
    assert event.request_sha256==svc.hash_body({'handoff_id':str(row.id),**request.model_dump(mode='json')})

@pytest.mark.asyncio
@pytest.mark.parametrize('semantics,reference,reason',[
    ('source_datetime_unverified',None,'source_receipt_effective_date_unverified'),
    ('source_datetime_utc','DBN-RECEIPT:'+str(uuid4()),'unmatched_dbn_receipt_reference'),
])
async def test_external_receipt_ambiguous_date_or_origin_holds(db_session,monkeypatch,semantics,reference,reason):
    t,a,c,original,p,b=await context(db_session,monkeypatch)
    row=await svc.prepare(db_session,t.id,a,b,'prepare')
    p['summary'].observed_at=datetime.now(timezone.utc)+timedelta(seconds=1)
    row,_=await svc.activate(db_session,row,a,SourceVersionRequest(expected_version=1,expected_source_capture_sha256='a'*64,expected_source_revision='b'*64),'activate')
    p['allocations']={'alloc1':{'id':'alloc1','amount':{'amount':'200.00','currency':'USD'},'payment':{'id':'receipt1','date_source':'2026-10-20T12:00:00Z','date_semantics':semantics,'dbn_receipt_reference':reference}}}
    _,result=await svc.reconcile(db_session,row,a,ReconcileRequest(expected_version=row.version,source_capture_sha256='a'*64,expected_source_revision='b'*64),'reconcile')
    assert result=={'conflict':reason}
    from app.db.models.payment import Payment
    assert await db_session.scalar(select(func.count()).select_from(Payment))==0

@pytest.mark.asyncio
async def test_external_receipt_once_preserves_effective_date_no_accounting(db_session,monkeypatch):
    from app.db.models.payment import Payment
    from app.db.models.invoice_settlement import InvoiceSettlement,PaymentAccountingLink
    from app.db.models.provider_outbox import ProviderOutboxEvent
    t,a,c,original,p,b=await context(db_session,monkeypatch)
    row=await svc.prepare(db_session,t.id,a,b,'prepare')
    p['summary'].observed_at=datetime.now(timezone.utc)+timedelta(seconds=1)
    row,_=await svc.activate(db_session,row,a,SourceVersionRequest(expected_version=1,expected_source_capture_sha256='a'*64,expected_source_revision='b'*64),'activate')
    p['allocations']={'alloc1':{'id':'alloc1','amount':{'amount':'200.00','currency':'USD'},'payment':{'id':'receipt1','date_source':'2026-10-20T12:00:00Z','date_semantics':'source_datetime_utc'}}}
    request=ReconcileRequest(expected_version=row.version,source_capture_sha256='a'*64,expected_source_revision='b'*64)
    _,result=await svc.reconcile(db_session,row,a,request,'reconcile')
    assert result is None
    await db_session.flush()
    assert (await svc.reconcile(db_session,row,a,request,'reconcile'))[1] is None
    receipt=await db_session.scalar(select(Payment))
    assert receipt.amount==Decimal('200') and receipt.created_at.isoformat().startswith('2026-10-20T12:00:00')
    settlement=await db_session.scalar(select(InvoiceSettlement).where(InvoiceSettlement.invoice_id==row.native_invoice_id))
    assert settlement.confirmed_principal==Decimal('200')
    assert await db_session.scalar(select(func.count()).select_from(PaymentAccountingLink))==0
    assert await db_session.scalar(select(func.count()).select_from(ProviderOutboxEvent))==0
    assert original.total_amount==Decimal('1000')

@pytest.mark.asyncio
async def test_ack_requires_attributable_marker_not_just_same_amount(db_session,monkeypatch):
    from app.db.models.payment import Payment,PaymentStatus,PaymentMethod
    from app.db.models.source_debt_handoff import EtsReceiptUpdateTask,SourceReceiptLink
    from app.schemas.source_debt_handoff import AcknowledgeRequest
    t,a,c,original,p,b=await context(db_session,monkeypatch)
    row=await svc.prepare(db_session,t.id,a,b,'prepare')
    p['summary'].observed_at=datetime.now(timezone.utc)+timedelta(seconds=1)
    row,_=await svc.activate(db_session,row,a,SourceVersionRequest(expected_version=1,expected_source_capture_sha256='a'*64,expected_source_revision='b'*64),'activate')
    receipt=Payment(id=uuid4(),tenant_id=t.id,invoice_id=row.native_invoice_id,payment_number='DB149-RECEIPT',amount=Decimal('200'),method=PaymentMethod.OTHER,status=PaymentStatus.COMPLETED)
    db_session.add(receipt);await db_session.flush()
    task=EtsReceiptUpdateTask(id=uuid4(),tenant_id=t.id,handoff_id=row.id,invoice_id=row.native_invoice_id,payment_id=receipt.id,principal_amount=Decimal('200'),received_amount=Decimal('200'),fee_amount=0,unapplied_amount=0,currency='USD',effective_at=datetime.now(timezone.utc),expected_source_revision='b'*64,state='claimed',version=1,claimed_by=a.id,claim_expires_at=datetime.now(timezone.utc)+timedelta(minutes=30))
    db_session.add(task);await db_session.flush()
    p['allocations']={'alloc1':{'id':'alloc1','amount':{'amount':'200.00','currency':'USD'},'payment':{'id':'receipt1'}}}
    request=AcknowledgeRequest(expected_version=1,source_capture_sha256='a'*64,expected_source_revision='b'*64,source_allocation_ids=['alloc1'])
    with pytest.raises(SettlementDomainError) as exc:
        await svc.acknowledge_task(db_session,task,a,request,'ack')
    assert exc.value.code=='source_receipt_attribution_unverified'
    p['allocations']['alloc1']['payment']['dbn_receipt_reference']='DBN-RECEIPT:'+str(receipt.id)
    await svc.acknowledge_task(db_session,task,a,request,'ack')
    await db_session.flush()
    assert task.state=='verified'
    assert await db_session.scalar(select(func.count()).select_from(Payment))==1
    assert await db_session.scalar(select(func.count()).select_from(SourceReceiptLink))==1
    assert (await svc.acknowledge_task(db_session,task,a,request,'ack')).state=='verified'

@pytest.mark.asyncio
async def test_collection_receivable_once_on_archived_imported_order(db_session,monkeypatch):
    from app.services.customer_receivables import account_snapshot
    from app.api.v1.endpoints.invoice_settlements import settlement_summary
    from app.db.models.invoice_settlement import InvoiceSettlement
    t,a,c,original,p,b=await context(db_session,monkeypatch)
    t.timezone='America/New_York'
    original.source='easy_truck_shop_import';original.repair_order.source='easy_truck_shop_import'
    original.repair_order.deleted_at=datetime.now(timezone.utc)
    row=await svc.prepare(db_session,t.id,a,b,'prepare')
    p['summary'].observed_at=datetime.now(timezone.utc)+timedelta(seconds=1)
    row,_=await svc.activate(db_session,row,a,SourceVersionRequest(expected_version=1,expected_source_capture_sha256='a'*64,expected_source_revision='b'*64),'activate')
    snapshot=await account_snapshot(db_session,tenant_id=t.id,customer_id=c.id)
    assert snapshot['native']['collectible']=='600.00'
    assert snapshot['native']['unverified_invoice_count']==0
    native_rows=[r for r in snapshot['rows'] if r['kind']=='invoice'] if 'rows' in snapshot else []
    if native_rows:assert len(native_rows)==1
    async def unavailable(*args,**kwargs):svc.fail('source_evidence_unavailable','Source unavailable')
    monkeypatch.setattr(svc,'source_proof',unavailable)
    settlement=await db_session.scalar(select(InvoiceSettlement).where(InvoiceSettlement.invoice_id==row.native_invoice_id))
    result=await settlement_summary(db_session,settlement,t,audience='staff',current_user=a)
    assert result.outstanding_balance==Decimal('600')
    assert not result.allowed_actions.create_attempt

@pytest.mark.asyncio
async def test_collection_provider_gate_and_accounting_exclusions(db_session,monkeypatch):
    from app.core.config import settings
    from app.services.quickbooks_sync_service import enqueue_quickbooks_invoice_sync
    from app.services.paid_invoice_webhook_service import enqueue_conversion_event
    t,a,c,original,p,b=await context(db_session,monkeypatch)
    row=await svc.prepare(db_session,t.id,a,b,'prepare')
    p['summary'].observed_at=datetime.now(timezone.utc)+timedelta(seconds=1)
    row,_=await svc.activate(db_session,row,a,SourceVersionRequest(expected_version=1,expected_source_capture_sha256='a'*64,expected_source_revision='b'*64),'activate')
    assert (await svc.summary(db_session,row))['collection_enabled'] is True
    monkeypatch.setattr(settings,'INVOICE_SPLIT_PAYMENTS_ENABLED',False)
    result=await svc.summary(db_session,row)
    assert result['collection_enabled'] is False
    assert 'split_payment_global_gate_disabled' in result['payment_hold_reasons']
    native=await db_session.get(Invoice,row.native_invoice_id)
    assert await enqueue_quickbooks_invoice_sync(db_session,invoice=native) is None
    assert await enqueue_conversion_event(db_session,tenant=t,invoice=native,order=original.repair_order,customer=c,event_type='repair_order.paid',idempotency_key='test') is None
    from app.services.invoice_payment_presentation import InvoicePaymentSummary
    body=svc.collection_email_html(native,result,InvoicePaymentSummary(state='unpaid',applied_amount='0.00',balance_due='600.00',basis='settlement'),'https://example.test/invoice',t)
    assert 'Transferred balance' in body and '600.00' in body and 'new sale or tax invoice' in body
    assert 'Qty/Hrs' not in body and '>Labor<' not in body
    history=svc.collection_email_html(original,{**result,'is_source_history':True,'balance_due':'0.00'},InvoicePaymentSummary(state='unpaid',balance_due='600.00'),'https://example.test/history',t)
    assert 'Historical source invoice' in history
    assert 'Current linked DBN balance: $0.00' in history
    assert 'not a separate payment request' in history

@pytest.mark.asyncio
async def test_dashboard_revenue_links_payment_invoice_and_tenant(db_session,monkeypatch):
    from app.api.v1.endpoints.dashboard import get_dashboard_stats
    from app.api.v1.endpoints import dashboard
    from sqlalchemy import Date,cast as sqlalchemy_cast
    # SQLite CAST(datetime AS DATE) returns a year integer; emulate PG date cast.
    monkeypatch.setattr(dashboard,'cast',lambda expression,target:func.date(expression) if target is Date else sqlalchemy_cast(expression,target))
    from app.db.models.payment import Payment,PaymentMethod,PaymentStatus
    from test_db048_invoice_settlements import _add_eligible_invoice
    t,a,c,original,p,b=await context(db_session,monkeypatch)
    other,other_owner,other_customer,other_invoice=await _financial_context(db_session,monkeypatch)
    await _add_eligible_invoice(db_session,tenant=other,customer=other_customer,reference_invoice=other_invoice,with_shadow_settlement=False)
    db_session.add_all([
        Payment(tenant_id=t.id,invoice_id=original.id,payment_number='DB149-DASH-OWN',amount=Decimal('100'),method=PaymentMethod.OTHER,status=PaymentStatus.COMPLETED),
        Payment(tenant_id=other.id,invoice_id=other_invoice.id,payment_number='DB149-DASH-OTHER',amount=Decimal('999'),method=PaymentMethod.OTHER,status=PaymentStatus.COMPLETED),
    ])
    await db_session.commit()
    result=await get_dashboard_stats(db=db_session,current_user=a)
    assert Decimal(result.revenue.today)==Decimal('100')
    assert Decimal(result.revenue.this_month)==Decimal('100')

@pytest.mark.asyncio
async def test_accounting_export_holds_linked_debt_preserves_unhanded_source(db_session,monkeypatch):
    from app.api.v1.endpoints.fleet_invoice_exports import _invoice_query
    t,a,c,original,p,b=await context(db_session,monkeypatch)
    original.billed_customer_id=c.id
    row=await svc.prepare(db_session,t.id,a,b,'prepare')
    p['summary'].observed_at=datetime.now(timezone.utc)+timedelta(seconds=1)
    row,_=await svc.activate(db_session,row,a,SourceVersionRequest(expected_version=1,expected_source_capture_sha256='a'*64,expected_source_revision='b'*64),'activate')
    exported=(await db_session.execute(_invoice_query(NS(tenant_id=t.id,customer_id=c.id)))).all()
    assert exported == []  # No duplicate invoice, stale original update, or tombstone.
    from test_db048_invoice_settlements import _add_eligible_invoice
    untouched=await _add_eligible_invoice(db_session,tenant=t,customer=c,reference_invoice=original,with_shadow_settlement=False)
    untouched.billed_customer_id=c.id
    untouched.source='easy_truck_shop_import'
    exported=(await db_session.execute(_invoice_query(NS(tenant_id=t.id,customer_id=c.id)))).all()
    assert [item[0].id for item in exported]==[untouched.id]
    assert original.total_amount==Decimal('1000')

@pytest.mark.asyncio
async def test_complete_financial_export_explicit_hold_no_receiver_deletion(db_session,monkeypatch):
    from app.api.v1.endpoints.fleet_repair_financial_exports import repair_financial_manifest
    from fastapi import Response,HTTPException
    from starlette.requests import Request
    t,a,c,original,p,b=await context(db_session,monkeypatch)
    await svc.prepare(db_session,t.id,a,b,'prepare')
    request=Request({'type':'http','query_string':b''})
    with pytest.raises(HTTPException) as exc:
        await repair_financial_manifest(request,Response(),db=db_session,key=NS(tenant_id=t.id,customer_id=c.id))
    assert exc.value.status_code==409
    assert exc.value.detail['code']=='external_manual_accounting_hold'
    # Another bill-to in the same tenant is outside the held customer scope.
    result=await repair_financial_manifest(request,Response(),db=db_session,key=NS(tenant_id=t.id,customer_id=uuid4()))
    assert result['items']==[]

@pytest.mark.asyncio
async def test_conflicted_collection_retains_known_balance_with_receivable_hold(db_session,monkeypatch):
    from app.services.customer_receivables import account_snapshot
    from app.db.models.invoice_settlement import InvoiceSettlement
    t,a,c,original,p,b=await context(db_session,monkeypatch)
    t.timezone='America/New_York'
    row=await svc.prepare(db_session,t.id,a,b,'prepare')
    p['summary'].observed_at=datetime.now(timezone.utc)+timedelta(seconds=1)
    row,_=await svc.activate(db_session,row,a,SourceVersionRequest(expected_version=1,expected_source_capture_sha256='a'*64,expected_source_revision='b'*64),'activate')
    settlement=await db_session.scalar(select(InvoiceSettlement).where(InvoiceSettlement.invoice_id==row.native_invoice_id))
    settlement.confirmed_principal=Decimal('300')
    row.state='source_conflict'
    snapshot=await account_snapshot(db_session,tenant_id=t.id,customer_id=c.id)
    assert snapshot['native']['collectible']=='0.00'
    assert snapshot['native']['held_collection_balance']=='300.00'
    assert snapshot['native']['collection_review_count']==1
    assert snapshot['native']['review_required_count']==1
    assert snapshot['native']['unverified_invoice_count']==1
    transaction=next(r for r in snapshot['transactions'] if r['kind']=='invoice')
    assert transaction['remaining_principal']=='300.00'
    assert transaction['source_owner']=='review_required'
