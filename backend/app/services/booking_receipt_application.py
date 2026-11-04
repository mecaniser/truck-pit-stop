"""Atomic, exact-payer application of an existing booking liability to a sale.

No provider call or synthetic Payment/credit tender is made here.
"""
from decimal import Decimal
from uuid import uuid4
from sqlalchemy import select,func
from sqlalchemy.orm import selectinload
from app.db.models.appointment import Appointment, AppointmentStatus
from app.db.models.booking_payment import BookingReceipt, BookingPaymentAttempt
from app.db.models.booking_application import BookingReceiptApplication, BookingAccountingReviewTask
from app.db.models.booking_fulfillment import BookingRepairOrderLink
from app.db.models.invoice import Invoice, InvoiceStatus
from app.db.models.repair_order import RepairOrder, RepairOrderStatus
from app.db.models.tenant import Tenant
from app.db.models.customer import Customer
from app.db.models.vehicle import Vehicle
from app.services import booking_payments as booking
from app.services.booking_fulfillment import staff, actor_name
from app.services.booking_application_accounting import receipt_balances, _receipt_source, ensure_manual_accounting_tasks
from app.services.financial_transaction_lock import lock_tenant_financials
from app.services.native_invoice_economics import native_invoice_economics

class _ApplicationScope:
    def __init__(self, db, tenant_id, order_id):
        self.db=db; self.transaction=db.sync_session.get_transaction();self.tenant_id=tenant_id;self.order_id=order_id
    def matches(self,db,tenant_id,order_id):
        return db is self.db and db.sync_session.get_transaction() is self.transaction and (tenant_id,order_id)==(self.tenant_id,self.order_id)

async def _order(db,apt,*,lock=False):
    if not apt.repair_order_id:return None
    statement=select(RepairOrder).where(RepairOrder.tenant_id==apt.tenant_id,RepairOrder.id==apt.repair_order_id).options(selectinload(RepairOrder.customer),selectinload(RepairOrder.vehicle))
    if lock:statement=statement.with_for_update()
    return await db.scalar(statement.execution_options(populate_existing=True))

async def _eligibility(db,apt,receipt,order):
    from app.services.booking_refund_verification import unresolved_refund_verification
    if await unresolved_refund_verification(db,apt.tenant_id,apt.id):return 'booking_refund_verification_pending'
    if not receipt or not order: return 'booking_intake_link_required'
    link=await db.scalar(select(BookingRepairOrderLink).where(BookingRepairOrderLink.tenant_id==apt.tenant_id,BookingRepairOrderLink.appointment_id==apt.id,BookingRepairOrderLink.repair_order_id==order.id))
    if (not link or order.deleted_at or order.source not in (None,'','native') or order.is_internal or order.customer_id!=apt.customer_id or order.vehicle_id!=link.reviewed_vehicle_id
        or apt.booking_payment_version!=1 or apt.booking_payment_state!='paid' or apt.status not in {AppointmentStatus.CONFIRMED,AppointmentStatus.IN_PROGRESS,AppointmentStatus.COMPLETED}):return 'booking_application_binding_invalid'
    if not order.customer or order.customer.tenant_id!=apt.tenant_id or order.customer.deleted_at or not order.vehicle or order.vehicle.tenant_id!=apt.tenant_id or order.vehicle.deleted_at:return 'booking_application_binding_invalid'
    if order.status!=RepairOrderStatus.COMPLETED:return 'booking_repair_order_not_completed'
    if await db.scalar(select(BookingPaymentAttempt.id).where(BookingPaymentAttempt.tenant_id==apt.tenant_id,BookingPaymentAttempt.appointment_id==apt.id,BookingPaymentAttempt.state.in_(booking.LIVE)).limit(1)):return 'booking_receipt_verification_pending'
    if receipt.refunded_amount_minor:return 'booking_receipt_refund_review_required'
    if await db.scalar(select(Invoice.id).where(Invoice.tenant_id==apt.tenant_id,Invoice.repair_order_id==order.id).limit(1)):return 'booking_invoice_already_issued'
    await _receipt_source(db,receipt)
    return None

async def prepayment_view(db,apt,*,invoice_options=None):
    from app.services.booking_refund_verification import unresolved_refund_verification
    refund_pending=await unresolved_refund_verification(db,apt.tenant_id,apt.id)
    receipt=await db.scalar(select(BookingReceipt).where(BookingReceipt.tenant_id==apt.tenant_id,BookingReceipt.id==apt.confirmed_receipt_id).execution_options(populate_existing=True))
    order=await _order(db,apt)
    application=await db.scalar(select(BookingReceiptApplication).where(BookingReceiptApplication.tenant_id==apt.tenant_id,BookingReceiptApplication.appointment_id==apt.id).order_by(BookingReceiptApplication.created_at.desc()).limit(1))
    tasks=(await db.scalars(select(BookingAccountingReviewTask).where(BookingAccountingReviewTask.tenant_id==apt.tenant_id,BookingAccountingReviewTask.receipt_id==receipt.id))).all() if receipt else []
    balances=None;block=None;preview=None
    if receipt:
        try:
            balances=await receipt_balances(db,apt.tenant_id,receipt.id)
            block=await _eligibility(db,apt,receipt,order)
        except Exception as exc:
            from app.services.invoice_settlement_service import SettlementDomainError
            if not isinstance(exc,SettlementDomainError):raise
            block=exc.code
            applied=int(await db.scalar(select(func.coalesce(func.sum(BookingReceiptApplication.amount_minor),0)).where(BookingReceiptApplication.tenant_id==apt.tenant_id,BookingReceiptApplication.receipt_id==receipt.id)) or 0)
            balances={'received_minor':receipt.amount_received_minor,'refunded_minor':receipt.refunded_amount_minor,'applied_minor':applied,'unapplied_minor':None,'version':receipt.version,'payment_verification_required':True,'balance_state':'review_required'}
    else:block='booking_receipt_unavailable'
    tenant=await db.get(Tenant,apt.tenant_id)
    if not block and tenant and balances:
        try:
            economics=await native_invoice_economics(db,order,tenant,discount_amount=(invoice_options or {}).get('discount_amount',Decimal(0)))
            preview=economics.preview(balances['unapplied_minor'])
            if not preview['suggested_apply_minor']:block='booking_receipt_application_unavailable'
        except Exception as exc:
            from app.services.invoice_settlement_service import SettlementDomainError
            if not isinstance(exc,SettlementDomainError):raise
            block=exc.code
    invoice=await db.get(Invoice,application.invoice_id) if application else None
    from app.services.invoice_payment_presentation import load_payment_summary
    summary=await load_payment_summary(db,invoice) if invoice else None
    customer=await db.scalar(select(Customer).where(Customer.id==apt.customer_id,Customer.tenant_id==apt.tenant_id))
    vehicle=await db.scalar(select(Vehicle).where(Vehicle.id==(order.vehicle_id if order else apt.vehicle_id),Vehicle.tenant_id==apt.tenant_id)) if (order or apt.vehicle_id) else None
    states={task.state for task in tasks}
    accounting_state='needs_review' if refund_pending or 'needs_review' in states else 'externally_reconciled' if tasks and states=={'externally_reconciled'} else 'awaiting_manual_ack'
    result={'appointment_id':str(apt.id),'repair_order_id':str(apt.repair_order_id) if apt.repair_order_id else None,
        'invoice_id':str(application.invoice_id) if application else None,'application_id':str(application.id) if application else None,
        'booking_version':apt.booking_version,'refund_verification_pending':refund_pending,'receipt':({'id':str(receipt.id),'provider':receipt.provider,'currency':receipt.currency,**balances} if balances else None),
        'invoice_payment_summary':summary.model_dump() if summary else None,'invoice_preview':preview,
        'accounting':{'mode':'external_manual','state':accounting_state,'review_task_id':str(tasks[0].id) if tasks else None,'export_hold':bool(application or tasks),'tasks':[{'id':str(t.id),'object_kind':t.object_kind,'state':t.state,'version':t.version,'amount_minor':t.amount_minor,'currency':t.currency,'evidence_snapshot_sha256':t.evidence_snapshot_sha256} for t in tasks]},
        'can_apply':not block,'application_block_reason':{'code':block,'message':'Review the reservation, completed intake, and receipt before applying prepayment.'} if block else None,
        'shop_timezone':tenant.timezone if tenant else None,
        'customer':{'id':str(customer.id),'display_name':' '.join(filter(None,[customer.first_name,customer.last_name])),'company_name':customer.company_name} if customer else None,
        'vehicle':{key:getattr(vehicle,key) for key in ('unit_number','year','make','model','license_plate')}|{'id':str(vehicle.id)} if vehicle else None}
    if application:
        from app.db.models.invoice_settlement import InvoiceSettlement
        settlement=await db.get(InvoiceSettlement,application.settlement_id)
        result['settlement_version']=settlement.version if settlement else None
    return result

async def issue_and_apply(db,actor,identity,body,request_key):
    staff(actor);request_key=booking.key(request_key)
    fingerprint=booking.digest({'appointment_id':identity,**body.model_dump()})
    await lock_tenant_financials(db,actor.tenant_id)
    apt=await booking.admitted_appointment(db,actor,identity,write=True)
    replay=await db.scalar(select(BookingReceiptApplication).where(BookingReceiptApplication.tenant_id==actor.tenant_id,BookingReceiptApplication.idempotency_key==request_key))
    if replay:
        if replay.appointment_id!=identity or replay.request_sha256!=fingerprint:booking.fail('idempotency_conflict','This key belongs to a different invoice application.')
        return await prepayment_view(db,apt)
    receipt=await db.scalar(select(BookingReceipt).where(BookingReceipt.tenant_id==apt.tenant_id,BookingReceipt.id==body.receipt_id,BookingReceipt.id==apt.confirmed_receipt_id).with_for_update().execution_options(populate_existing=True))
    order=await _order(db,apt,lock=True)
    if not receipt or not order or order.id!=body.repair_order_id:booking.fail('booking_application_binding_invalid','Review the exact receipt and intake before issuing.')
    if apt.booking_version!=body.expected_booking_version or receipt.version!=body.expected_receipt_version:booking.fail('booking_application_version_conflict','This prepayment changed. Refresh before issuing.')
    block=await _eligibility(db,apt,receipt,order)
    if block:booking.fail(block,'Review the completed intake and verified receipt before issuing.')
    balances=await receipt_balances(db,apt.tenant_id,receipt.id,lock=True)
    tenant=await db.scalar(select(Tenant).where(Tenant.id==apt.tenant_id).with_for_update().execution_options(populate_existing=True))
    options=body.invoice_options.model_dump()
    economics=await native_invoice_economics(db,order,tenant,discount_amount=options.get('discount_amount') or Decimal(0),lock=True)
    if economics.sha256!=body.expected_invoice_economics_sha256:
        from fastapi import HTTPException
        raise HTTPException(409,{'code':'booking_invoice_economics_changed','message':'Invoice pricing changed. Review the current preview.','invoice_preview':economics.preview(balances['unapplied_minor'])})
    if body.amount_minor>balances['unapplied_minor'] or body.amount_minor>int(economics.principal_total*100):booking.fail('booking_application_amount_unavailable','The requested amount exceeds available receipt or invoice principal.')
    attempt,_,config=await _receipt_source(db,receipt)
    async def attach(invoice,settlement,issued_economics):
        if issued_economics.sha256!=economics.sha256:booking.fail('booking_invoice_economics_changed','Invoice pricing changed before publication.')
        application=BookingReceiptApplication(id=uuid4(),tenant_id=apt.tenant_id,receipt_id=receipt.id,appointment_id=apt.id,
            repair_order_id=order.id,invoice_id=invoice.id,settlement_id=settlement.id,customer_id=apt.customer_id,
            amount_minor=body.amount_minor,currency='usd',receipt_version_before=receipt.version,booking_version_before=apt.booking_version,
            provider=attempt.provider,provider_account_id=attempt.provider_account_id,environment=attempt.environment,
            configuration_version=attempt.configuration_version,qbo_realm_snapshot=config.qbo_realm_snapshot,
            receipt_proof_sha256=receipt.proof_sha256,invoice_economics_sha256=economics.sha256,
            actor_user_id=actor.id,actor_name_snapshot=actor_name(actor),idempotency_key=request_key,request_sha256=fingerprint)
        db.add(application);await db.flush()
        receipt.version+=1;apt.booking_version+=1
        principal=Decimal(body.amount_minor)/100
        settlement.confirmed_principal=principal
        from app.services.invoice_settlement_service import settlement_state,append_ledger_event
        settlement.state=settlement_state(settlement);settlement.version+=1
        settlement.accounting_sync_status='external_manual'
        settlement.qbo_realm_snapshot=config.qbo_realm_snapshot
        settlement.initial_provider_configuration_version=attempt.configuration_version
        await db.flush()  # accounting authority reads refresh identity-map state
        await ensure_manual_accounting_tasks(db,receipt=receipt,application=application)
        await append_ledger_event(db,settlement=settlement,event_type='booking_prepayment_applied',idempotency_key=f'booking-application:{application.id}',actor=actor,prior_state='unpaid',new_state=settlement.state,principal_delta=principal,evidence={'booking_receipt_application_id':str(application.id),'booking_receipt_id':str(receipt.id)})
        if settlement.state=='paid':
            invoice.status=InvoiceStatus.PAID;invoice.paid_at=booking.now();order.status=RepairOrderStatus.PAID
        await db.flush()
    from app.api.v1.endpoints.invoices import auto_create_invoice_for_order
    scope=_ApplicationScope(db,apt.tenant_id,order.id)
    db.info['_booking_invoice_application_scope']=scope
    try:
        invoice=await auto_create_invoice_for_order(db,order,tenant,actor.id,commit=False,notify=False,_booking_application=attach,_invoice_options=options)
        if invoice is None:booking.fail('booking_invoice_already_issued','An invoice already exists for this intake.')
    finally:
        db.info.pop('_booking_invoice_application_scope',None)
    from app.api.v1.endpoints.invoices import enqueue_invoice_created_email
    await enqueue_invoice_created_email(db,invoice=invoice,order=order,tenant=tenant)
    await db.commit()
    return await prepayment_view(db,apt)


async def invalidate_application_settlements(db,tenant_id,receipt_id):
    """Advance read authority after a new verified refund; no money rewrite."""
    from app.db.models.invoice_settlement import InvoiceSettlement
    identities=(await db.scalars(select(BookingReceiptApplication.settlement_id).where(BookingReceiptApplication.tenant_id==tenant_id,BookingReceiptApplication.receipt_id==receipt_id))).all()
    if identities:
        rows=(await db.scalars(select(InvoiceSettlement).where(InvoiceSettlement.tenant_id==tenant_id,InvoiceSettlement.id.in_(identities)).order_by(InvoiceSettlement.id).with_for_update().execution_options(populate_existing=True))).all()
        for row in rows:row.version+=1
