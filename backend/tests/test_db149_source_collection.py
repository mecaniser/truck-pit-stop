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
    assert native.line_items_snapshot['labor']==[]
    assert Decimal(native.line_items_snapshot['collection'][0]['amount'])==Decimal('600')
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

@pytest.mark.asyncio
async def test_overview_customer_vehicle_and_sort_count_debt_once(db_session,monkeypatch):
    from app.services.customer_balance import customer_balance_totals,vehicle_balance_totals,customer_balance_sort
    from app.db.models.customer import Customer
    from app.db.models.invoice_settlement import InvoiceSettlement
    t,a,c,original,p,b=await context(db_session,monkeypatch)
    original.source='easy_truck_shop_import'
    row=await svc.prepare(db_session,t.id,a,b,'prepare')
    p['summary'].observed_at=datetime.now(timezone.utc)+timedelta(seconds=1)
    row,_=await svc.activate(db_session,row,a,SourceVersionRequest(expected_version=1,expected_source_capture_sha256='a'*64,expected_source_revision='b'*64),'activate')
    settlement=await db_session.scalar(select(InvoiceSettlement).where(InvoiceSettlement.invoice_id==row.native_invoice_id))
    settlement.confirmed_principal=Decimal('300')
    row.state='source_conflict'
    native,legacy=await customer_balance_totals(db_session,[c.id])
    assert native[c.id]==Decimal('300') and legacy[c.id]==0
    vehicle_id=original.repair_order.vehicle_id
    vehicle_native,vehicle_legacy=await vehicle_balance_totals(db_session,c.id,[vehicle_id])
    assert vehicle_native[vehicle_id]==Decimal('300') and vehicle_legacy[vehicle_id]==0
    # Operational outstanding balance stays known under a collection hold.
    amount=await db_session.scalar(select(customer_balance_sort()).select_from(Customer).where(Customer.id==c.id))
    assert Decimal(str(amount))==Decimal('300')

@pytest.mark.asyncio
async def test_reviewed_different_portal_billto_exact_membership_and_history(db_session,monkeypatch):
    from app.db.models.customer import Customer
    from app.db.models.user import UserRole
    from app.schemas.source_debt_handoff import BillToReview
    from app.api.v1.endpoints.invoices import get_invoice,download_invoice_pdf,_list_invoices_legacy
    from app.api.v1.endpoints.invoice_settlements import invoice_for_principal
    from app.api.v1.endpoints.invoice_access import _load_hardened_guest_invoice_context
    t,a,source,original,p,b=await context(db_session,monkeypatch)
    original.source='easy_truck_shop_import';source.ets_external_id='97052'
    original.due_date=datetime(2026,10,19,tzinfo=timezone.utc)
    target=Customer(tenant_id=t.id,first_name='Reviewed',last_name='Portal',company_name='Same legal business',email='target@example.test')
    db_session.add(target);await db_session.flush()
    p.update(source_customer=source,customer=target)
    p['latest'].update(source_customer_id='97052',source_customer_uuid=str(uuid4()),source_customer_deleted=False,source_customer_binding_kind='embedded_service_customer')
    target_prepare=b.model_copy(update={'target_customer_id':target.id})
    preview=await svc.preview(db_session,t.id,original.id,target.id)
    assert preview['hold_reasons']==['bill_to_review_required']
    with pytest.raises(SettlementDomainError) as exc:
        await svc.prepare(db_session,t.id,a,target_prepare,'missing-review')
    assert exc.value.code=='bill_to_review_required'
    target_prepare.bill_to_review=BillToReview(mode='owner_same_legal_entity',source_customer_id=source.id,target_customer_id=target.id,attested_same_legal_entity=True,confirmation_reference='Owner instruction for exact ETS1687',reason='Same legal business, use existing portal account')
    row=await svc.prepare(db_session,t.id,a,target_prepare,'prepare')
    assert row.source_customer_id==source.id and row.customer_id==target.id
    assert row.bill_to_authorization['actor_user_id']==str(a.id)
    assert row.bill_to_authorization_sha256==svc.hash_body(row.bill_to_authorization)
    assert await db_session.scalar(select(func.count()).select_from(Invoice))==1
    assert (await svc.prepare(db_session,t.id,a,target_prepare,'prepare')).id==row.id
    p['summary'].observed_at=datetime.now(timezone.utc)+timedelta(seconds=1)
    row,_=await svc.activate(db_session,row,a,SourceVersionRequest(expected_version=1,expected_source_capture_sha256='a'*64,expected_source_revision='b'*64),'activate')
    native=await db_session.get(Invoice,row.native_invoice_id)
    b_user=NS(role=UserRole.CUSTOMER,customer_id=target.id,tenant_id=t.id)
    a_user=NS(role=UserRole.CUSTOMER,customer_id=source.id,tenant_id=t.id)
    detail=await get_invoice(native.id,db=db_session,current_user=b_user)
    assert detail.customer_name=='Reviewed Portal'
    assert svc.utc(native.due_date)==svc.utc(original.due_date)
    assert (await invoice_for_principal(db_session,native.id,b_user))[2]==target.id
    for denied in (a_user,NS(role=UserRole.CUSTOMER,customer_id=uuid4(),tenant_id=t.id),NS(role=UserRole.CUSTOMER,customer_id=target.id,tenant_id=uuid4())):
        with pytest.raises(Exception):await get_invoice(native.id,db=db_session,current_user=denied)
        with pytest.raises(SettlementDomainError):await invoice_for_principal(db_session,native.id,denied)
        with pytest.raises(Exception):await download_invoice_pdf(native.id,db=db_session,current_user=denied)
    listed=await _list_invoices_legacy(status_filter=None,repair_order_id=None,skip=0,limit=100,paginated=False,db=db_session,current_user=b_user)
    assert [i.id for i in listed]==[native.id]
    assert await svc.can_view_source_history(db_session,original,target.id)
    history=await get_invoice(original.id,db=db_session,current_user=b_user)
    assert history.source_collection['is_source_history']
    source_view=await get_invoice(original.id,db=db_session,current_user=a_user)
    assert source_view.source_collection['restricted_history']
    assert source_view.source_collection['native_invoice_id'] is None
    assert source_view.source_collection['target_customer_id'] is None
    assert source_view.source_collection['balance_due'] is None
    assert 'source_capture_sha256' not in source_view.source_collection
    a_list=await _list_invoices_legacy(status_filter=None,repair_order_id=None,skip=0,limit=100,paginated=False,db=db_session,current_user=a_user)
    assert [i.id for i in a_list]==[original.id]
    assert a_list[0].source_collection['restricted_history']
    assert (await download_invoice_pdf(native.id,db=db_session,current_user=b_user)).media_type=='application/pdf'
    token=dict(invoice_id=str(native.id),tenant_id=str(t.id),customer_id=str(target.id))
    assert (await _load_hardened_guest_invoice_context(db_session,token))[2].id==target.id
    with pytest.raises(SettlementDomainError):await _load_hardened_guest_invoice_context(db_session,{**token,'customer_id':str(source.id)})
    assert original.repair_order.customer_id==source.id and original.billed_customer_id is None
    from app.services.customer_balance import customer_balance_totals,vehicle_balance_totals,customer_balance_sort
    totals,legacy=await customer_balance_totals(db_session,[source.id,target.id])
    assert totals.get(source.id,Decimal('0'))==0 and totals[target.id]==Decimal('600')
    vehicle_totals,_=await vehicle_balance_totals(db_session,target.id,[original.repair_order.vehicle_id])
    assert vehicle_totals[original.repair_order.vehicle_id]==Decimal('600')
    assert Decimal(str(await db_session.scalar(select(customer_balance_sort()).select_from(Customer).where(Customer.id==target.id))))==Decimal('600')
    with pytest.raises(Exception):await get_invoice(original.id,db=db_session,current_user=NS(role=UserRole.CUSTOMER,customer_id=target.id,tenant_id=uuid4()))
    from app.services.invoice_settlement_service import create_attempt
    from app.db.models.invoice_settlement import InvoiceSettlement,InvoicePaymentLedgerEvent
    settlement=await db_session.scalar(select(InvoiceSettlement).where(InvoiceSettlement.invoice_id==native.id))
    from app.services.invoice_settlement_service import provider_readiness
    readiness=await provider_readiness(db_session,t,invoice_id=native.id,lock_ancestry=True)
    assert readiness.status=='ready',readiness.reasons
    creation=await create_attempt(db_session,invoice=native,tenant=t,customer_id=target.id,actor=a,amount=Decimal('600'),rail='card',expected_settlement_version=settlement.version,idempotency_key='target-attempt',source='customer_portal',subject_type='customer',subject_id=target.id,sender_evidence={'source_collection_admission':'client-forgery'})
    evidence=await db_session.scalar(select(InvoicePaymentLedgerEvent).where(InvoicePaymentLedgerEvent.attempt_id==creation.attempt.id,InvoicePaymentLedgerEvent.event_type=='attempt_created'))
    admission=evidence.evidence_snapshot['source_collection_admission']
    assert admission['handoff_id']==str(row.id) and admission['source_capture_sha256']=='a'*64
    assert admission['source_revision']=='b'*64
    from app.services.invoice_settlement_service import confirm_attempt
    from app.db.models.source_debt_handoff import EtsReceiptUpdateTask
    confirmation=await confirm_attempt(db_session,attempt_id=creation.attempt.id,tenant=t,actor=a,
        expected_attempt_version=creation.attempt.version,idempotency_key='confirm-target',received_principal=Decimal('600'),
        reference='pi_fictional',provider_charge_id='ch_fictional',provider_event_id='evt_fictional')
    assert confirmation.paid_transition and native.status.value=='paid'
    task=await db_session.scalar(select(EtsReceiptUpdateTask).where(EtsReceiptUpdateTask.payment_id==confirmation.payment.id))
    assert task.handoff_id==row.id and task.principal_amount==Decimal('600')
    assert original.status.value=='sent' and original.repair_order.status.value=='invoiced'
    source_view=await get_invoice(original.id,db=db_session,current_user=a_user)
    assert source_view.source_collection['balance_due'] is None
    assert source_view.source_collection['native_confirmed_principal'] is None
    from test_db048_invoice_settlements import _add_eligible_invoice
    unrelated=await _add_eligible_invoice(db_session,tenant=t,customer=source,reference_invoice=original,with_shadow_settlement=False)
    unrelated.source='easy_truck_shop_import'
    with pytest.raises(Exception):await get_invoice(unrelated.id,db=db_session,current_user=b_user)
    changed=target_prepare.model_copy(deep=True)
    changed.bill_to_review.reason='Different claim'
    with pytest.raises(SettlementDomainError) as exc:
        await svc.prepare(db_session,t.id,a,changed,'different-claim')
    assert exc.value.code=='bill_to_review_conflict'
    for deleted_customer in (source,target):
        deleted_customer.deleted_at=datetime.now(timezone.utc)
        with pytest.raises(SettlementDomainError):await svc.effective_billing_customer(db_session,native,original.repair_order)
        assert not await svc.can_view_source_history(db_session,original,target.id)
        deleted_customer.deleted_at=None
        await db_session.flush()
    # A malformed proof never grants even the otherwise correct native target.
    row.bill_to_authorization_sha256='f'*64
    with pytest.raises(SettlementDomainError):await svc.effective_billing_customer(db_session,native,original.repair_order)

@pytest.mark.asyncio
async def test_real_source_proof_requires_original_remote_customer_for_alias(db_session,monkeypatch):
    from app.db.models.customer import Customer
    from test_db139_imported_billing import snapshot_fixture
    from app.services.ets_source_evidence import _digest
    real_proof=svc.source_proof
    t,a,source,original,p,b=await context(db_session,monkeypatch)
    monkeypatch.setattr(svc,'source_proof',real_proof)
    source.ets_external_id='97052'
    original.source=svc.SOURCE;original.invoice_number='ETSINV-9001';original.subtotal=original.total_amount=Decimal('534.41')
    original.repair_order.source=svc.SOURCE;original.repair_order.order_number='ETS-7001-8002'
    target=Customer(tenant_id=t.id,first_name='Portal',last_name='Target',email='proof-target@example.test')
    db_session.add(target);await db_session.flush()
    _,_,envelope=snapshot_fixture(invoice_status='5',balance={'amount':'534.41','currency':'USD'},payment_lines=[])
    monkeypatch.setattr(svc.imported_billing,'_source_evidence',AsyncMock(return_value={original.id:envelope}))
    monkeypatch.setattr(svc.imported_billing,'trusted_shop_binding',lambda tenant:('shop1',None))
    with pytest.raises(SettlementDomainError) as exc:
        await real_proof(db_session,t.id,original.id,target.id,allow_bill_to_review=True)
    assert exc.value.code=='source_customer_evidence_unavailable'
    facts=envelope['observations'][0]['evidence']
    facts.update(source_customer_id='97052',source_customer_uuid=str(uuid4()),source_customer_deleted=False,source_customer_binding_kind='embedded_service_customer')
    envelope['observations'][0]['sha256']=_digest(facts)
    verified=await real_proof(db_session,t.id,original.id,target.id,allow_bill_to_review=True)
    assert verified['source_customer'].id==source.id and verified['customer'].id==target.id
    for owner,field in ((source,'is_internal_fleet'),(original.repair_order,'is_internal')):
        setattr(owner,field,True)
        with pytest.raises(SettlementDomainError) as exc:
            await real_proof(db_session,t.id,original.id,target.id,allow_bill_to_review=True)
        assert exc.value.code=='source_identity_unresolved'
        setattr(owner,field,False)
        await db_session.flush()
    # Present conflicting proof holds either mode, including same-customer legacy flows.
    good=dict(facts)
    for change in ({'source_customer_id':'OTHER'},{'source_customer_deleted':True},{'source_customer_uuid':'invalid'}):
        facts.clear();facts.update(good|change)
        envelope['observations'][0]['sha256']=_digest(facts)
        for bill_to in (source.id,target.id):
            with pytest.raises(SettlementDomainError) as exc:
                await real_proof(db_session,t.id,original.id,bill_to,allow_bill_to_review=True)
            assert exc.value.code=='source_customer_evidence_unavailable'
    with pytest.raises(SettlementDomainError) as exc:
        await real_proof(db_session,uuid4(),original.id,target.id,allow_bill_to_review=True)
    assert exc.value.status_code==404
