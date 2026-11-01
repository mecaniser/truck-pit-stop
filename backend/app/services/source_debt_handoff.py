"""Verified source-debt handoff. No provider/ETS calls or implicit customer delivery."""
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from hashlib import sha256
import json
from types import SimpleNamespace
from uuid import uuid4
from sqlalchemy import select, or_, and_
from app.db.models.invoice import Invoice, InvoiceStatus
from app.db.models.repair_order import RepairOrder
from app.db.models.customer import Customer
from app.db.models.invoice_settlement import InvoiceSettlement, InvoicePaymentAttempt
from app.db.models.payment import Payment, PaymentStatus, PaymentMethod
from app.db.models.source_debt_handoff import SourceDebtHandoff, SourceDebtEvent, EtsReceiptUpdateTask, SourceReceiptLink
from app.services.financial_transaction_lock import lock_tenant_financials
from app.services.invoice_settlement_service import SettlementDomainError, money, ZERO
from app.services import imported_billing
from app.services.ets_source_evidence import latest_source_evidence, _digest

COLLECTION_POLICY='source_collection_hold'
COLLECTION_SOURCE='ets_collection_handoff'
SOURCE='easy_truck_shop_import'

def is_collection(invoice):
    return getattr(invoice,'accounting_policy',None)==COLLECTION_POLICY or getattr(invoice,'source',None)==COLLECTION_SOURCE or getattr(invoice,'source_debt_handoff_id',None) is not None

def fail(code,message,status=409):
    raise SettlementDomainError(code,message,status_code=status)

def hash_body(body):
    return sha256(json.dumps(body,sort_keys=True,separators=(',',':'),default=str).encode()).hexdigest()

def utc(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)

async def source_proof(db, tenant_id, invoice_id, customer_id):
    invoice=await db.scalar(select(Invoice).where(Invoice.id==invoice_id,Invoice.tenant_id==tenant_id))
    customer=await db.scalar(select(Customer).where(Customer.id==customer_id,Customer.tenant_id==tenant_id,Customer.deleted_at.is_(None)))
    if not invoice or not customer:
        fail('source_invoice_not_found','Source invoice or customer not found.',404)
    order=await db.scalar(select(RepairOrder).where(RepairOrder.id==invoice.repair_order_id,RepairOrder.tenant_id==tenant_id))
    if (invoice.source!=SOURCE or invoice.deleted_at or invoice.status==InvoiceStatus.CANCELLED or invoice.voided_at
        or not order or order.source!=SOURCE or str(getattr(order.status,'value',order.status))=='cancelled'
        or order.customer_id!=customer.id or invoice.billed_customer_id not in (None,customer.id)
        or customer.is_internal_fleet or invoice.is_internal or not order.vehicle_id):
        fail('source_identity_unresolved','Exact source invoice and legal customer identity require review.')
    envelope=(await imported_billing._source_evidence(db,tenant_id,[invoice.id])).get(invoice.id)
    shop,error=imported_billing.trusted_shop_binding(tenant_id)
    # Only this proven historical reference may be soft archived. No ORM/source mutation.
    historical=SimpleNamespace(id=order.id,tenant_id=order.tenant_id,source=order.source,deleted_at=None,order_number=order.order_number)
    try:
        summary=imported_billing._source_summary(invoice,envelope,historical,shop)
        if error or summary.payment_status=='unverified' or summary.review_required:
            fail('source_evidence_unavailable','A fresh complete source observation is required.')
        latest=latest_source_evidence(envelope)
    except SettlementDomainError:
        raise
    except Exception as exc:
        fail('source_evidence_unavailable','A fresh complete source observation is required: '+str(exc)[:100])
    # Exactly one source invoice for the entire source service, including soft archives.
    siblings=list((await db.scalars(select(RepairOrder).where(RepairOrder.tenant_id==tenant_id,
        RepairOrder.source==SOURCE,RepairOrder.order_number.like(f"ETS-{latest['service_id']}-%")))).all())
    sibling_ids=[o.id for o in siblings]
    if order.id not in sibling_ids or any(o.customer_id!=customer.id or o.vehicle_id!=order.vehicle_id for o in siblings):
        fail('source_job_identity_conflict','Source service/customer/vehicle linkage requires review.')
    invoices=list((await db.scalars(select(Invoice).where(Invoice.tenant_id==tenant_id,Invoice.repair_order_id.in_(sibling_ids),Invoice.accounting_policy!=COLLECTION_POLICY))).all())
    candidate,reason=imported_billing.supported_invoice(invoices)
    if reason or not candidate or candidate.id!=invoice.id:
        fail('source_invoice_ambiguous','A unique canonical source invoice is required.')
    allocations={str(row['id']):row for row in latest.get('payment_lines',[])}
    if len(allocations)!=len(latest.get('payment_lines',[])):
        fail('source_allocation_conflict','Source allocation identities conflict.')
    revision=str(envelope['observations'][-1]['sha256'])
    return dict(invoice=invoice,order=order,customer=customer,envelope=envelope,latest=latest,summary=summary,
        digest=_digest(latest),revision=revision,allocations=allocations,shop=shop)

def proposal(proof):
    s,l=proof['summary'],proof['latest']
    return dict(source_invoice_id=str(proof['invoice'].id),source_repair_order_id=str(proof['order'].id),
        source_shop_id=proof['shop'],source_service_number=str(l['service_id']),source_invoice_number=str(l['invoice_number']),
        source_internal_invoice_id=str(l['invoice_id']),source_observed_at=s.observed_at.isoformat(),
        source_capture_sha256=proof['digest'],source_revision=proof['revision'],currency='USD',
        original_issued_total=str(s.total_amount),source_prior_allocated=str(s.recorded_completed_amount),
        opening_principal=str(s.recorded_remaining_amount),target_customer_id=str(proof['customer'].id),
        original_invoice_date=proof['invoice'].ets_invoiced_at.isoformat() if proof['invoice'].ets_invoiced_at else None)

async def preview(db,tenant_id,invoice_id,customer_id):
    existing=await db.scalar(select(SourceDebtHandoff).where(SourceDebtHandoff.tenant_id==tenant_id,SourceDebtHandoff.source_dbn_invoice_id==invoice_id,SourceDebtHandoff.customer_id==customer_id))
    existing_summary=await summary(db,existing) if existing else None
    try:
        proof=await source_proof(db,tenant_id,invoice_id,customer_id)
        if money(proof['summary'].recorded_remaining_amount)<=ZERO:
            return dict(eligibility='held',hold_reasons=['source_already_settled'],proposal=proposal(proof),existing_handoff=existing_summary)
        return dict(eligibility='ready',hold_reasons=[],proposal=proposal(proof),existing_handoff=existing_summary)
    except SettlementDomainError as exc:
        if exc.status_code==404:raise
        return dict(eligibility='held',hold_reasons=[exc.code],proposal=None,existing_handoff=existing_summary)

async def get_handoff(db,tenant_id,handoff_id,lock=False):
    query=select(SourceDebtHandoff).where(SourceDebtHandoff.id==handoff_id,SourceDebtHandoff.tenant_id==tenant_id,SourceDebtHandoff.deleted_at.is_(None))
    if lock:query=query.with_for_update()
    row=await db.scalar(query)
    if not row:fail('handoff_not_found','Source debt handoff not found.',404)
    return row

async def event(db,handoff,actor,kind,key,body,task=None,request_body=None):
    digest=hash_body(request_body if request_body is not None else body)
    old=await db.scalar(select(SourceDebtEvent).where(SourceDebtEvent.tenant_id==handoff.tenant_id,SourceDebtEvent.request_key==key))
    if old:
        if old.request_sha256!=digest:fail('idempotency_conflict','Idempotency key was used for a different request.')
        return old
    row=SourceDebtEvent(tenant_id=handoff.tenant_id,handoff_id=handoff.id,task_id=task.id if task else None,
        actor_user_id=getattr(actor,'id',None),event_type=kind,request_key=key,request_sha256=digest,version=handoff.version,evidence=body)
    db.add(row)
    return row

async def prepare(db,tenant_id,actor,body,key):
    await lock_tenant_financials(db,tenant_id)
    payload=body.model_dump(mode='json');request_hash=hash_body(payload)
    old=await db.scalar(select(SourceDebtHandoff).where(SourceDebtHandoff.tenant_id==tenant_id,SourceDebtHandoff.idempotency_key==key))
    if old:
        if old.request_sha256!=request_hash:fail('idempotency_conflict','Idempotency key was used for a different request.')
        return old
    proof=await source_proof(db,tenant_id,body.source_invoice_id,body.target_customer_id)
    if proof['digest']!=body.expected_source_capture_sha256 or proof['revision']!=body.expected_source_revision:
        fail('source_version_changed','Source evidence changed. Refresh the preview.')
    if money(proof['summary'].recorded_remaining_amount)<=ZERO:fail('source_already_settled','The source debt is already settled.')
    l=proof['latest']
    existing=await db.scalar(select(SourceDebtHandoff).where(SourceDebtHandoff.tenant_id==tenant_id,SourceDebtHandoff.ets_shop_id==proof['shop'],SourceDebtHandoff.ets_invoice_internal_id==str(l['invoice_id'])))
    if existing:
        if existing.customer_id!=body.target_customer_id or existing.source_dbn_invoice_id!=body.source_invoice_id:fail('source_identity_conflict','This debt already has a different collection identity.')
        return existing
    row=SourceDebtHandoff(id=uuid4(),tenant_id=tenant_id,source_kind='easy_truck_shop',ets_shop_id=proof['shop'],
        ets_service_internal_id=str(l['service_internal_id']),ets_invoice_internal_id=str(l['invoice_id']),
        source_invoice_number=str(l['invoice_number']),source_service_number=str(l['service_id']),
        source_dbn_invoice_id=proof['invoice'].id,source_repair_order_id=proof['order'].id,customer_id=body.target_customer_id,
        source_capture_document=proof['envelope'],source_capture_sha256=proof['digest'],source_observed_at=proof['summary'].observed_at,
        original_issued_total=proof['summary'].total_amount,source_prior_allocated=proof['summary'].recorded_completed_amount,
        opening_principal=proof['summary'].recorded_remaining_amount,currency='USD',state='prepared',source_revision=proof['revision'],version=1,
        owner_acknowledged_at=datetime.now(timezone.utc),owner_acknowledged_by=actor.id,accounting_state='external_reconciliation_pending',accounting_owner='external_manual',
        idempotency_key=key,request_sha256=request_hash)
    db.add(row);await db.flush()
    await event(db,row,actor,'prepared','prepare:'+key,payload)
    return row

async def pending_activity(db,invoice_ids,tenant_id):
    return await db.scalar(select(InvoicePaymentAttempt.id).where(InvoicePaymentAttempt.tenant_id==tenant_id,
        InvoicePaymentAttempt.invoice_id.in_(invoice_ids),or_(InvoicePaymentAttempt.state=='pending',InvoicePaymentAttempt.received_amount>0,InvoicePaymentAttempt.provider_charge_id.is_not(None))).limit(1))

async def activate(db,row,actor,body,key):
    await lock_tenant_financials(db,row.tenant_id)
    row=await get_handoff(db,row.tenant_id,row.id,True)
    payload=body.model_dump(mode='json')
    replay=await db.scalar(select(SourceDebtEvent).where(SourceDebtEvent.tenant_id==row.tenant_id,SourceDebtEvent.request_key=='activate:'+key))
    if replay:
        if replay.request_sha256!=hash_body(payload):fail('idempotency_conflict','Idempotency key was used for a different request.')
        return row,True
    if row.native_invoice_id:
        if row.version!=body.expected_version:fail('stale_handoff_version','Handoff changed. Refresh before activating.')
        return row,True
    if row.state!='prepared' or row.version!=body.expected_version:fail('stale_handoff_version','Handoff changed. Refresh before activating.')
    proof=await source_proof(db,row.tenant_id,row.source_dbn_invoice_id,row.customer_id)
    if (proof['digest']!=body.expected_source_capture_sha256 or proof['revision']!=body.expected_source_revision
        or hash_body(latest_source_evidence(row.source_capture_document) | {'observed_at_source':None}) != hash_body(proof['latest'] | {'observed_at_source':None})
        or money(proof['summary'].recorded_remaining_amount)!=money(row.opening_principal)):
        fail('source_version_changed','Source allocations or balance changed. Prepare a reviewed proposal again.')
    if utc(proof['summary'].observed_at)<utc(row.owner_acknowledged_at):fail('source_post_ack_refresh_required','Refresh source evidence after the primary-collector acknowledgement before activation.')
    if await pending_activity(db,[row.source_dbn_invoice_id],row.tenant_id):fail('source_payment_conflict','Existing payment activity requires reconciliation.')
    invoice=Invoice(id=uuid4(),tenant_id=row.tenant_id,repair_order_id=row.source_repair_order_id,billed_customer_id=row.customer_id,
        source_debt_handoff_id=row.id,source=COLLECTION_SOURCE,accounting_policy=COLLECTION_POLICY,
        invoice_number='DBN-COL-'+row.id.hex[:20].upper(),status=InvoiceStatus.SENT,is_internal=False,
        recipient_name=(f'{proof["customer"].first_name} {proof["customer"].last_name}').strip(),
        recipient_email=proof['customer'].email,recipient_phone=proof['customer'].phone,
        subtotal=row.opening_principal,total_amount=row.opening_principal,shop_supplies_amount=ZERO,service_fee_amount=ZERO,tax_amount=ZERO,discount_amount=ZERO,
        notes=f'Collection copy of ETS invoice {row.source_invoice_number}; no new sale or tax.',
        line_items_snapshot={'version':1,'labor':[{'description':f'Balance transferred from ETS invoice {row.source_invoice_number}','hours':'1.00','hourly_rate':str(row.opening_principal),'total_cost':str(row.opening_principal)}],'parts':[]},
        quickbooks_sync_status='external_reconciliation_pending',created_by_user_id=actor.id)
    db.add(invoice);await db.flush()
    db.add(InvoiceSettlement(tenant_id=row.tenant_id,invoice_id=invoice.id,customer_id=row.customer_id,principal_total=row.opening_principal,
        max_card_fee=ZERO,max_card_fee_tax=ZERO,sales_tax_rate_snapshot=ZERO,card_fee_rate_snapshot=ZERO,currency='USD',state='unpaid',
        confirmed_principal=ZERO,active_pending_principal=ZERO,legacy_reconciliation_status='native',accounting_sync_status='external_reconciliation_pending'))
    row.native_invoice_id=invoice.id;row.state='active';row.version+=1;row.source_revision=proof['revision'];row.source_observed_at=proof['summary'].observed_at
    await event(db,row,actor,'activated','activate:'+key,payload)
    await db.flush()
    return row,False

async def summary(db,row):
    settlement=await db.scalar(select(InvoiceSettlement).where(InvoiceSettlement.tenant_id==row.tenant_id,InvoiceSettlement.invoice_id==row.native_invoice_id)) if row.native_invoice_id else None
    tasks=list((await db.scalars(select(EtsReceiptUpdateTask).where(EtsReceiptUpdateTask.tenant_id==row.tenant_id,EtsReceiptUpdateTask.handoff_id==row.id,EtsReceiptUpdateTask.state!='verified'))).all())
    holds=[]
    try:
        proof=await source_proof(db,row.tenant_id,row.source_dbn_invoice_id,row.customer_id)
        available=True
    except SettlementDomainError as exc:
        available=False;holds.append(exc.code)
    if row.state=='source_conflict':holds.append('source_receipt_conflict')
    if available and row.native_invoice_id:
        try:
            invoice=await db.scalar(select(Invoice).where(Invoice.id==row.native_invoice_id,Invoice.tenant_id==row.tenant_id))
            await invoice_handoff(db,invoice,require_active=True)
        except SettlementDomainError as exc:
            holds.append(exc.code)
    if row.state=='prepared':holds.append('handoff_not_active')
    # Collection visibility never implies configured payment capability.
    if row.native_invoice_id and available and not holds:
        from app.db.models.tenant import Tenant
        from app.services.invoice_settlement_service import provider_readiness
        tenant=await db.scalar(select(Tenant).where(Tenant.id==row.tenant_id))
        readiness=await provider_readiness(db,tenant,invoice_id=row.native_invoice_id)
        if readiness.status!='ready':holds.extend(readiness.reasons or ['payment_capability_unavailable'])
    return dict(id=str(row.id),source_invoice_id=str(row.source_dbn_invoice_id),state=row.state,version=row.version,source_invoice_number=row.source_invoice_number,
        source_service_number=row.source_service_number,original_issued_total=str(money(row.original_issued_total)),
        source_prior_allocated=str(money(row.source_prior_allocated)),opening_principal=str(money(row.opening_principal)),
        native_invoice_id=str(row.native_invoice_id) if row.native_invoice_id else None,
        balance_due=str(max(ZERO,money(settlement.principal_total)-money(settlement.confirmed_principal))) if settlement else None,
        native_confirmed_principal=str(money(settlement.confirmed_principal)) if settlement else '0.00',
        native_pending_principal=str(money(settlement.active_pending_principal)) if settlement else '0.00',
        source_observed_at=row.source_observed_at.isoformat(),source_sync_state='source_conflict' if row.state=='source_conflict' else 'source_unavailable' if not available else 'ets_update_pending' if tasks else 'current',
        accounting_state=row.accounting_state,hold_reasons=holds,collection_enabled=row.state=='active' and available and not holds,
        payment_hold_reasons=holds,source_capture_sha256=proof['digest'] if available else row.source_capture_sha256,
        source_revision=proof['revision'] if available else row.source_revision,
        original_invoice_date=proof['invoice'].ets_invoiced_at.isoformat() if available and proof['invoice'].ets_invoiced_at else None)

async def invoice_handoff(db,invoice,*,require_active=False,check_source=True):
    if not is_collection(invoice):return None
    if (invoice.source!=COLLECTION_SOURCE or invoice.accounting_policy!=COLLECTION_POLICY or not invoice.source_debt_handoff_id
        or invoice.deleted_at or invoice.status==InvoiceStatus.CANCELLED or invoice.voided_at):
        fail('collection_lineage_invalid','Collection invoice lineage requires review.')
    row=await get_handoff(db,invoice.tenant_id,invoice.source_debt_handoff_id)
    if row.native_invoice_id!=invoice.id or row.source_repair_order_id!=invoice.repair_order_id or row.customer_id!=invoice.billed_customer_id:
        fail('collection_lineage_invalid','Collection invoice customer and source linkage require review.')
    customer=await db.scalar(select(Customer.id).where(Customer.id==row.customer_id,Customer.tenant_id==row.tenant_id,Customer.deleted_at.is_(None)))
    if not customer:fail('invoice_not_found','Invoice not found.',404)
    if require_active and row.state!='active':fail('collection_not_active','This source debt is not available for collection.')
    if check_source:
        proof=await source_proof(db,row.tenant_id,row.source_dbn_invoice_id,row.customer_id)
        links=list((await db.scalars(select(SourceReceiptLink).where(SourceReceiptLink.tenant_id==row.tenant_id,SourceReceiptLink.handoff_id==row.id))).all())
        original=latest_source_evidence(row.source_capture_document)
        known={str(x['id']):hash_body(x) for x in original.get('payment_lines',[])}
        known.update({x.source_allocation_id:x.content_sha256 for x in links})
        current={k:hash_body(v) for k,v in proof['allocations'].items()}
        if known!=current:fail('source_reconciliation_required','Source payments changed. Reconcile before collecting another payment.')
    return row

async def source_collection_for_invoice(db,invoice):
    if not is_collection(invoice):
        if getattr(invoice,'source',None)!=SOURCE:return None
        row=await db.scalar(select(SourceDebtHandoff).where(SourceDebtHandoff.tenant_id==invoice.tenant_id,SourceDebtHandoff.source_dbn_invoice_id==invoice.id,SourceDebtHandoff.native_invoice_id.is_not(None)))
        if row:return {**await summary(db,row),'is_source_history':True}
        return None
    row=await invoice_handoff(db,invoice,check_source=False)
    return {**await summary(db,row),'is_source_history':False}

def task_dto(task):
    return {**{k:str(getattr(task,k)) if getattr(task,k) is not None else None for k in ('id','handoff_id','invoice_id','payment_id','attempt_id')},
        **{k:str(money(getattr(task,k))) for k in ('principal_amount','received_amount','fee_amount','unapplied_amount')},
        'currency':task.currency,'effective_at':task.effective_at.isoformat(),'state':task.state,'version':task.version,
        'receipt_reference':'DBN-RECEIPT:'+str(task.payment_id),'expected_source_revision':task.expected_source_revision,'claim_expires_at':task.claim_expires_at.isoformat() if task.claim_expires_at else None}

async def record_native_receipt(db,invoice,payment,attempt,actor=None):
    row=await invoice_handoff(db,invoice,check_source=False)
    if not row:return None
    old=await db.scalar(select(EtsReceiptUpdateTask).where(EtsReceiptUpdateTask.tenant_id==row.tenant_id,EtsReceiptUpdateTask.payment_id==payment.id))
    if old:return old
    principal=money(attempt.applied_principal_amount)
    if principal<=ZERO:return None
    task=EtsReceiptUpdateTask(id=uuid4(),tenant_id=row.tenant_id,handoff_id=row.id,invoice_id=invoice.id,payment_id=payment.id,attempt_id=attempt.id,
        principal_amount=principal,received_amount=money(attempt.provider_charge_amount),fee_amount=money(attempt.applied_card_fee_amount)+money(attempt.applied_card_fee_tax_amount),
        unapplied_amount=money(attempt.unapplied_amount),currency='USD',effective_at=attempt.confirmed_at or datetime.now(timezone.utc),expected_source_revision=row.source_revision,
        state='pending_manual',version=1)
    db.add(task);row.version+=1;await db.flush()
    await event(db,row,actor,'native_receipt_confirmed','receipt:'+str(payment.id),{'payment_id':str(payment.id),'principal_amount':str(principal),'ets_automatically_updated':False},task)
    return task

async def task_for_tenant(db,tenant_id,task_id,lock=False):
    q=select(EtsReceiptUpdateTask).where(EtsReceiptUpdateTask.tenant_id==tenant_id,EtsReceiptUpdateTask.id==task_id,EtsReceiptUpdateTask.deleted_at.is_(None))
    if lock:q=q.with_for_update()
    task=await db.scalar(q)
    if not task:fail('ets_task_not_found','ETS update task not found.',404)
    return task

async def claim_task(db,task,actor,body,key):
    await lock_tenant_financials(db,task.tenant_id)
    task=await task_for_tenant(db,task.tenant_id,task.id,True)
    row=await get_handoff(db,task.tenant_id,task.handoff_id,True)
    request={'task_id':str(task.id),**body.model_dump()}
    previous=await db.scalar(select(SourceDebtEvent).where(SourceDebtEvent.tenant_id==row.tenant_id,SourceDebtEvent.request_key=='claim:'+key))
    if previous:
        if previous.request_sha256!=hash_body(request):fail('idempotency_conflict','Idempotency key was used for a different request.')
        return task
    if task.version!=body.expected_version or task.state in ('verified','conflict'):fail('stale_task_version','Task changed. Refresh the task.')
    if task.claimed_by and task.claimed_by!=actor.id and task.claim_expires_at and utc(task.claim_expires_at)>datetime.now(timezone.utc):
        fail('ets_task_claimed','Another operator is handling this ETS update.')
    task.claimed_by=actor.id;task.claim_expires_at=datetime.now(timezone.utc)+timedelta(minutes=30);task.state='claimed';task.version+=1;row.version+=1
    await event(db,row,actor,'task_claimed','claim:'+key,request,task)
    return task

async def conflict(db,row,actor,key,reason,task=None,request=None):
    row.state='source_conflict';row.version+=1
    if task:task.state='conflict';task.version+=1
    await event(db,row,actor,'source_conflict',key,{'conflict':reason},task,request_body=request)
    return {'conflict':reason}

async def acknowledge_task(db,task,actor,body,key):
    await lock_tenant_financials(db,task.tenant_id)
    task=await task_for_tenant(db,task.tenant_id,task.id,True)
    row=await get_handoff(db,task.tenant_id,task.handoff_id,True)
    request={'task_id':str(task.id),**body.model_dump(mode='json')}
    previous=await db.scalar(select(SourceDebtEvent).where(SourceDebtEvent.tenant_id==row.tenant_id,SourceDebtEvent.request_key=='ack:'+key))
    if previous:
        if previous.request_sha256!=hash_body(request):fail('idempotency_conflict','Idempotency key was used for a different request.')
        return task
    if task.version!=body.expected_version:fail('stale_task_version','Task changed. Refresh the task.')
    if task.claimed_by!=actor.id or task.state not in ('claimed','awaiting_verification') or not task.claim_expires_at or utc(task.claim_expires_at)<datetime.now(timezone.utc):
        fail('ets_task_claim_required','Claim this task before acknowledging the manual ETS entry.')
    proof=await source_proof(db,row.tenant_id,row.source_dbn_invoice_id,row.customer_id)
    if proof['digest']!=body.source_capture_sha256 or proof['revision']!=body.expected_source_revision:
        fail('source_version_changed','Refresh the source before verifying the ETS update.')
    if utc(proof['summary'].observed_at)<utc(task.effective_at):fail('source_post_receipt_refresh_required','Refresh source evidence after recording the receipt.')
    ids=body.source_allocation_ids
    if len(set(ids))!=len(ids):fail('source_allocation_conflict','Source allocation IDs must be distinct.')
    baseline={str(x['id']) for x in latest_source_evidence(row.source_capture_document).get('payment_lines',[])}
    if any(k not in proof['allocations'] or k in baseline for k in ids):fail('source_allocation_unverified','Only new exact verified source allocations may acknowledge this receipt.')
    if any(proof['allocations'][k]['payment'].get('dbn_receipt_reference')!='DBN-RECEIPT:'+str(task.payment_id) for k in ids):fail('source_receipt_attribution_unverified','Fresh source allocations must carry the exact DBN receipt reference from this task.')
    amount=sum((imported_billing.amount(proof['allocations'][k]['amount']) for k in ids),ZERO)
    if money(amount)!=money(task.principal_amount):fail('source_allocation_amount_mismatch','Source allocations do not match the confirmed principal.')
    for k in ids:
        used=await db.scalar(select(SourceReceiptLink).where(SourceReceiptLink.tenant_id==row.tenant_id,SourceReceiptLink.ets_shop_id==row.ets_shop_id,SourceReceiptLink.ets_invoice_internal_id==row.ets_invoice_internal_id,SourceReceiptLink.source_allocation_id==k))
        if used and (used.task_id!=task.id or used.content_sha256!=hash_body(proof['allocations'][k])):fail('source_allocation_reused','This source allocation already belongs to another receipt.')
    for k in ids:
        used=await db.scalar(select(SourceReceiptLink.id).where(SourceReceiptLink.tenant_id==row.tenant_id,SourceReceiptLink.handoff_id==row.id,SourceReceiptLink.source_allocation_id==k))
        if not used:
            item=proof['allocations'][k]
            db.add(SourceReceiptLink(tenant_id=row.tenant_id,handoff_id=row.id,ets_shop_id=row.ets_shop_id,ets_invoice_internal_id=row.ets_invoice_internal_id,
                source_allocation_id=k,source_payment_id=str(item['payment']['id']),source_revision=proof['revision'],source_capture_sha256=proof['digest'],
                content_sha256=hash_body(item),amount=imported_billing.amount(item['amount']),effective_at=task.effective_at,origin='dbn_ack',native_payment_id=task.payment_id,task_id=task.id))
    task.state='verified';task.verified_at=datetime.now(timezone.utc);task.version+=1
    row.version+=1;row.source_revision=proof['revision'];row.source_observed_at=proof['summary'].observed_at
    await event(db,row,actor,'ets_receipt_acknowledged','ack:'+key,request,task)
    return task

async def reconcile(db,row,actor,body,key):
    await lock_tenant_financials(db,row.tenant_id)
    row=await get_handoff(db,row.tenant_id,row.id,True)
    request=body.model_dump(mode='json')
    previous=await db.scalar(select(SourceDebtEvent).where(SourceDebtEvent.tenant_id==row.tenant_id,SourceDebtEvent.request_key=='reconcile:'+key))
    if previous:
        if previous.request_sha256!=hash_body(request):fail('idempotency_conflict','Idempotency key was used for a different request.')
        return row,({'conflict':previous.evidence['conflict']} if previous.evidence.get('conflict') else None)
    if row.version!=body.expected_version:fail('stale_handoff_version','Handoff changed. Refresh before reconciling.')
    if not row.native_invoice_id or row.state not in ('active','source_conflict'):fail('handoff_not_active','Activate the collection copy before receipt reconciliation.')
    proof=await source_proof(db,row.tenant_id,row.source_dbn_invoice_id,row.customer_id)
    if proof['digest']!=body.source_capture_sha256 or proof['revision']!=body.expected_source_revision:fail('source_version_changed','Refresh the source before reconciling.')
    if money(proof['summary'].total_amount)!=money(row.original_issued_total):
        return row,await conflict(db,row,actor,'reconcile:'+key,'source_invoice_total_changed',request=request)
    baseline={str(x['id']):hash_body(x) for x in latest_source_evidence(row.source_capture_document).get('payment_lines',[])}
    links=list((await db.scalars(select(SourceReceiptLink).where(SourceReceiptLink.tenant_id==row.tenant_id,SourceReceiptLink.handoff_id==row.id))).all())
    known={**baseline,**{x.source_allocation_id:x.content_sha256 for x in links}}
    if any(k not in proof['allocations'] or hash_body(proof['allocations'][k])!=v for k,v in known.items()):
        return row,await conflict(db,row,actor,'reconcile:'+key,'source_receipt_changed_or_removed',request=request)
    incoming=[(k,v) for k,v in proof['allocations'].items() if k not in known]
    tasks=list((await db.scalars(select(EtsReceiptUpdateTask).where(EtsReceiptUpdateTask.tenant_id==row.tenant_id,EtsReceiptUpdateTask.handoff_id==row.id,EtsReceiptUpdateTask.state!='verified'))).all())
    inflight=await db.scalar(select(InvoicePaymentAttempt.id).where(InvoicePaymentAttempt.tenant_id==row.tenant_id,InvoicePaymentAttempt.invoice_id==row.native_invoice_id,or_(InvoicePaymentAttempt.state=='pending',and_(InvoicePaymentAttempt.state.not_in(['confirmed','refunded','reversed']),InvoicePaymentAttempt.provider_charge_id.is_not(None)))).limit(1))
    if incoming and (tasks or inflight):
        return row,await conflict(db,row,actor,'reconcile:'+key,'source_receipt_requires_origin_review',request=request)
    invoice=await db.scalar(select(Invoice).where(Invoice.id==row.native_invoice_id,Invoice.tenant_id==row.tenant_id))
    if invoice is None:fail('collection_not_found','Collection invoice not found.',404)
    settlement=await db.scalar(select(InvoiceSettlement).where(InvoiceSettlement.invoice_id==invoice.id,InvoiceSettlement.tenant_id==row.tenant_id).with_for_update())
    if not invoice or invoice.deleted_at or invoice.status==InvoiceStatus.CANCELLED or not settlement:fail('collection_not_found','Collection invoice not found.',404)
    total_incoming=sum((imported_billing.amount(v['amount']) for _,v in incoming),ZERO)
    if total_incoming>max(ZERO,money(settlement.principal_total)-money(settlement.confirmed_principal)):
        return row,await conflict(db,row,actor,'reconcile:'+key,'external_receipt_exceeds_remaining_balance',request=request)
    source_dates={}
    for k,item in incoming:
        p=item['payment']
        try:
            if p.get('date_semantics')!='source_datetime_utc':raise ValueError('unverified source date')
            stamp=datetime.fromisoformat(p['date_source'].replace('Z','+00:00'))
            if stamp.tzinfo is None or stamp.utcoffset()!=timedelta(0):raise ValueError('ambiguous source date')
            source_dates[k]=stamp
        except (ValueError,KeyError,TypeError):
            return row,await conflict(db,row,actor,'reconcile:'+key,'source_receipt_effective_date_unverified',request=request)
        if p.get('dbn_receipt_reference'):
            return row,await conflict(db,row,actor,'reconcile:'+key,'unmatched_dbn_receipt_reference',request=request)
    from app.services.payment_number_service import allocate_next_payment_number
    from app.services.invoice_settlement_service import append_ledger_event,settlement_state
    for k,item in incoming:
        amount=imported_billing.amount(item['amount'])
        # Only the validated source-effective UTC time enters the receipt period.
        payment=Payment(id=uuid4(),tenant_id=row.tenant_id,invoice_id=invoice.id,payment_number=await allocate_next_payment_number(db,row.tenant_id),amount=amount,
            method=PaymentMethod.OTHER,status=PaymentStatus.COMPLETED,source='ets_external_receipt',recorded_by_user_id=actor.id,
            notes='Verified ETS source allocation '+k,created_at=source_dates[k])
        db.add(payment);await db.flush()
        db.add(SourceReceiptLink(tenant_id=row.tenant_id,handoff_id=row.id,ets_shop_id=row.ets_shop_id,ets_invoice_internal_id=row.ets_invoice_internal_id,
            source_allocation_id=k,source_payment_id=str(item['payment']['id']),source_revision=proof['revision'],source_capture_sha256=proof['digest'],
            content_sha256=hash_body(item),amount=amount,effective_at=source_dates[k],origin='ets_external',native_payment_id=payment.id))
        settlement.confirmed_principal=money(settlement.confirmed_principal)+amount
        await append_ledger_event(db,settlement=settlement,event_type='external_source_receipt',idempotency_key='ets-allocation:'+row.ets_shop_id+':'+row.ets_invoice_internal_id+':'+k,actor=actor,principal_delta=amount,
            evidence={'payment_id':str(payment.id),'source_allocation_id':k,'no_provider_charge':True,'source_capture_sha256':proof['digest']})
    settlement.state=settlement_state(settlement)
    if money(settlement.confirmed_principal)>=money(settlement.principal_total):
        invoice.status=InvoiceStatus.PAID;invoice.paid_at=invoice.paid_at or datetime.now(timezone.utc)
    row.source_revision=proof['revision'];row.source_observed_at=proof['summary'].observed_at;row.version+=1
    if not tasks:row.state='active'
    await event(db,row,actor,'source_reconciled','reconcile:'+key,request)
    return row,None


def source_history_alias_clause():
    return ~select(SourceDebtHandoff.id).where(SourceDebtHandoff.tenant_id==Invoice.tenant_id,SourceDebtHandoff.source_dbn_invoice_id==Invoice.id,SourceDebtHandoff.native_invoice_id.is_not(None)).correlate(Invoice).exists()

def collection_email_html(invoice,collection,payment_summary,invoice_access_url,tenant=None):
    from html import escape
    from app.services.invoice_payment_presentation import payment_summary_html
    from app.services.invoice_review_service import invoice_review_html
    number=escape(str(collection.get('source_invoice_number','')))
    date=escape(str(collection.get('original_invoice_date') or '')[:10])
    return (f'<h2>Collection copy — {escape(invoice.invoice_number)}</h2>'
        f'<p>Original ETS invoice {number} · Original date: {date}</p>'
        f'<p>Original issued total: ${Decimal(collection["original_issued_total"]):,.2f} · Prior ETS payments / credits: ${Decimal(collection["source_prior_allocated"]):,.2f}</p>'
        f'<p>Transferred balance: <b>${Decimal(collection["opening_principal"]):,.2f}</b>. Balance includes original charges. This copy is not a new sale or tax invoice.</p>'
        +payment_summary_html(payment_summary)
        +f'<p><a href="{escape(invoice_access_url,quote=True)}">View current invoice and receipt</a></p>'
        +invoice_review_html(tenant,invoice))
