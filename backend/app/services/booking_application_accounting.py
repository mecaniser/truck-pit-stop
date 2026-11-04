"""Booking liability reads and durable external/manual bookkeeping review.

No provider IO, Payment row, cash revenue, external accounting success or commit.
"""
from datetime import datetime, timezone
from decimal import Decimal
from hashlib import sha256
import json
from uuid import uuid4
from sqlalchemy import select, func, exists, and_
from app.db.models.appointment import Appointment
from app.db.models.booking_payment import BookingReceipt, BookingPaymentAttempt
from app.db.models.booking_application import (BookingReceiptApplication,
    BookingAccountingReviewTask, BookingAccountingReviewEvent)
from app.db.models.repair_order import RepairOrder
from app.db.models.invoice import Invoice
from app.db.models.invoice_settlement import InvoiceSettlement, TenantPaymentProviderConfiguration
from app.db.models.user import User, UserRole
from app.services.financial_transaction_lock import lock_tenant_financials


def _fail(code,message='Booking prepayment requires review.',status=409):
    from app.services.invoice_settlement_service import SettlementDomainError
    raise SettlementDomainError(code,message,status_code=status)


def _hash(data):
    return sha256(json.dumps(data,sort_keys=True,separators=(',',':'),default=str).encode()).hexdigest()


async def _fresh_scalar(db, statement):
    # SELECT FOR UPDATE locks the database row but does not overwrite a cached
    # ORM instance unless populate_existing is explicit. Every authority read
    # in this module must use committed database state after serialization.
    return await db.scalar(statement.execution_options(populate_existing=True))


async def receipt_balances(db,tenant_id,receipt_id,lock=False):
    if lock:await lock_tenant_financials(db,tenant_id)
    query=select(BookingReceipt).where(BookingReceipt.tenant_id==tenant_id,BookingReceipt.id==receipt_id)
    if lock:query=query.with_for_update()
    receipt=await _fresh_scalar(db, query)
    if not receipt:_fail('booking_receipt_not_found',status=404)
    applied=int(await _fresh_scalar(db, select(func.coalesce(func.sum(BookingReceiptApplication.amount_minor),0)).where(
        BookingReceiptApplication.tenant_id==tenant_id,BookingReceiptApplication.receipt_id==receipt_id)) or 0)
    received=receipt.amount_received_minor;refunded=receipt.refunded_amount_minor
    if received is None or refunded is None or min(received,refunded,applied)<0 or refunded+applied>received:
        _fail('booking_receipt_balance_invalid')
    return {'received_minor':received,'refunded_minor':refunded,'applied_minor':applied,
            'unapplied_minor':received-refunded-applied,'version':receipt.version}


async def applied_principal_for_invoice(db,tenant_id,invoice_id):
    amount=await _fresh_scalar(db, select(func.coalesce(func.sum(BookingReceiptApplication.amount_minor),0)).where(
        BookingReceiptApplication.tenant_id==tenant_id,BookingReceiptApplication.invoice_id==invoice_id))
    return (Decimal(amount or 0)/100).quantize(Decimal('.01'))


def invoice_export_hold_clause(tenant_id,invoice_id_column):
    # Applications themselves hold permanently, even if a task is missing or ACKed.
    return exists(select(BookingReceiptApplication.id).where(
        BookingReceiptApplication.tenant_id==tenant_id,
        BookingReceiptApplication.invoice_id==invoice_id_column)) | exists(select(BookingAccountingReviewTask.id).where(
        BookingAccountingReviewTask.tenant_id==tenant_id,
        BookingAccountingReviewTask.invoice_id==invoice_id_column))


async def invoice_has_booking_export_hold(db,tenant_id,invoice_id):
    return bool(await _fresh_scalar(db, select(invoice_export_hold_clause(tenant_id,invoice_id))))


async def _receipt_source(db,receipt):
    attempt=await _fresh_scalar(db, select(BookingPaymentAttempt).where(
        BookingPaymentAttempt.tenant_id==receipt.tenant_id,BookingPaymentAttempt.id==receipt.attempt_id,
        BookingPaymentAttempt.appointment_id==receipt.appointment_id))
    appointment=await _fresh_scalar(db, select(Appointment).where(Appointment.tenant_id==receipt.tenant_id,
        Appointment.id==receipt.appointment_id))
    config=await _fresh_scalar(db, select(TenantPaymentProviderConfiguration).where(
        TenantPaymentProviderConfiguration.tenant_id==receipt.tenant_id,
        TenantPaymentProviderConfiguration.version==(attempt.configuration_version if attempt else None)))
    if not attempt or not appointment or not config or not (
        attempt.state=='succeeded' and attempt.verified_at and receipt.proof_sha256 and len(receipt.proof_sha256)==64
        and receipt.verification_basis in {'server_retrieval','verified_connect_webhook'}
        and receipt.provider==attempt.provider==config.selected_provider
        and receipt.provider_account_id==attempt.provider_account_id==config.provider_account_snapshot
        and receipt.provider_intent_id==attempt.provider_intent_id
        and bool(receipt.charge_id) and bool(attempt.provider_charge_id)
        and receipt.charge_id==attempt.provider_charge_id
        and receipt.currency==attempt.currency=='usd'
        and receipt.amount_received_minor==attempt.amount_minor
        and appointment.customer_id==attempt.customer_id
        and appointment.booking_provider_configuration_version==attempt.configuration_version
        and appointment.booking_provider_environment==attempt.environment):
        _fail('booking_receipt_proof_invalid')
    return attempt,appointment,config


async def ensure_manual_accounting_tasks(db,*,receipt,application=None):
    await lock_tenant_financials(db,receipt.tenant_id)
    await receipt_balances(db,receipt.tenant_id,receipt.id,lock=True)
    receipt=await _fresh_scalar(db,select(BookingReceipt).where(
        BookingReceipt.tenant_id==receipt.tenant_id,BookingReceipt.id==receipt.id).with_for_update())
    attempt,appointment,config=await _receipt_source(db,receipt)
    specs=[('booking_receipt_liability',receipt.id,receipt.amount_received_minor,None,None)]
    if application is not None:
        uncertain=await _fresh_scalar(db, select(BookingPaymentAttempt.id).where(BookingPaymentAttempt.tenant_id==receipt.tenant_id,
            BookingPaymentAttempt.appointment_id==receipt.appointment_id,
            BookingPaymentAttempt.state.in_(['created','creating','requires_action','requires_payment_method','processing','outcome_unknown'])).limit(1))
        if uncertain:_fail('booking_receipt_verification_pending')
        if appointment.booking_payment_state!='paid' or appointment.status.value not in {'confirmed','in_progress','completed'}:_fail('booking_application_binding_invalid')
        if (application.tenant_id!=receipt.tenant_id or application.receipt_id!=receipt.id
            or application.appointment_id!=receipt.appointment_id
            or application.customer_id!=appointment.customer_id):_fail('booking_application_binding_invalid')
        invoice=await _fresh_scalar(db, select(Invoice).where(Invoice.tenant_id==receipt.tenant_id,Invoice.id==application.invoice_id))
        settlement=await _fresh_scalar(db, select(InvoiceSettlement).where(InvoiceSettlement.tenant_id==receipt.tenant_id,
            InvoiceSettlement.id==application.settlement_id,InvoiceSettlement.invoice_id==application.invoice_id))
        order=await _fresh_scalar(db, select(RepairOrder).where(RepairOrder.tenant_id==receipt.tenant_id,
            RepairOrder.id==application.repair_order_id))
        if (not invoice or not settlement or not order
            or appointment.repair_order_id!=order.id or invoice.repair_order_id!=order.id
            or settlement.customer_id!=application.customer_id or order.customer_id!=application.customer_id
            or (invoice.billed_customer_id or order.customer_id)!=application.customer_id
            or application.provider!=attempt.provider or application.provider_account_id!=attempt.provider_account_id
            or application.configuration_version!=attempt.configuration_version or application.environment!=attempt.environment
            or application.qbo_realm_snapshot!=config.qbo_realm_snapshot
            or application.receipt_proof_sha256!=receipt.proof_sha256):
            _fail('booking_application_binding_invalid')
        specs.append(('booking_receipt_application',application.id,application.amount_minor,application.id,application.invoice_id))
    tasks=[]
    for kind,object_id,amount,application_id,invoice_id in specs:
        task=await _fresh_scalar(db, select(BookingAccountingReviewTask).where(
            BookingAccountingReviewTask.tenant_id==receipt.tenant_id,
            BookingAccountingReviewTask.object_kind==kind,BookingAccountingReviewTask.financial_object_id==object_id,
            BookingAccountingReviewTask.operation_version==1).with_for_update())
        proof=_hash({'receipt':receipt.id,'receipt_proof':receipt.proof_sha256,'object':object_id,
            'kind':kind,'amount':amount,'provider':attempt.provider,'account':attempt.provider_account_id,
            'environment':attempt.environment,'config':attempt.configuration_version,'realm':config.qbo_realm_snapshot})
        if task:
            if task.evidence_snapshot_sha256!=proof or task.amount_minor!=amount:_fail('booking_accounting_proof_changed')
        else:
            task=BookingAccountingReviewTask(id=uuid4(),tenant_id=receipt.tenant_id,receipt_id=receipt.id,
                application_id=application_id,invoice_id=invoice_id,object_kind=kind,financial_object_id=object_id,
                operation_version=1,state='awaiting_manual_ack',version=1,provider=attempt.provider,
                provider_account_id=attempt.provider_account_id,environment=attempt.environment,
                configuration_version=attempt.configuration_version,qbo_realm_snapshot=config.qbo_realm_snapshot,
                amount_minor=amount,currency='usd',owning_writer='external_manual',evidence_snapshot_sha256=proof)
            db.add(task)
        tasks.append(task)
    await db.flush()
    return tasks


async def acknowledge_manual_accounting(db,*,tenant_id,appointment_id,task_id,actor,expected_version,
        idempotency_key,evidence_reference,external_company_reference,review_note,
        receipt_liability_recorded,application_to_ar_recorded):
    await lock_tenant_financials(db,tenant_id)
    staff=await _fresh_scalar(db, select(User).where(User.id==actor.id,User.tenant_id==tenant_id,
        User.is_active.is_(True),User.deleted_at.is_(None),User.role.in_([UserRole.GARAGE_OWNER,UserRole.GARAGE_ADMIN])))
    if not staff or actor.tenant_id!=tenant_id:_fail('booking_accounting_review_not_found',status=404)
    if (not isinstance(idempotency_key,str) or not 8<=len(idempotency_key.strip())<=200
        or not all(isinstance(x,str) and x.strip() for x in [evidence_reference,external_company_reference,review_note])
        or receipt_liability_recorded is not True or not isinstance(application_to_ar_recorded,bool)):
        _fail('booking_accounting_evidence_required',status=422)
    request_hash=_hash({'task_id':task_id,'appointment_id':appointment_id,'expected_version':expected_version,
        'evidence_reference':evidence_reference,'external_company_reference':external_company_reference,
        'review_note':review_note,'actor_id':staff.id,'receipt_liability_recorded':receipt_liability_recorded,
        'application_to_ar_recorded':application_to_ar_recorded})
    task=await _fresh_scalar(db, select(BookingAccountingReviewTask).join(BookingReceipt,and_(
        BookingReceipt.id==BookingAccountingReviewTask.receipt_id,
        BookingReceipt.tenant_id==BookingAccountingReviewTask.tenant_id)).where(
        BookingAccountingReviewTask.tenant_id==tenant_id,BookingAccountingReviewTask.id==task_id,
        BookingReceipt.appointment_id==appointment_id).with_for_update())
    if not task:_fail('booking_accounting_review_not_found',status=404)
    existing=await _fresh_scalar(db, select(BookingAccountingReviewEvent).where(
        BookingAccountingReviewEvent.tenant_id==tenant_id,BookingAccountingReviewEvent.idempotency_key==idempotency_key))
    if existing:
        if existing.task_id!=task.id or existing.request_sha256!=request_hash:_fail('idempotency_conflict')
        return task
    if task.version!=expected_version:_fail('booking_accounting_version_conflict')
    if not task.qbo_realm_snapshot or external_company_reference!=task.qbo_realm_snapshot:
        _fail('booking_accounting_mapping_required','Use the exact reviewed external company mapping before acknowledging bookkeeping.')
    if task.state!='awaiting_manual_ack':_fail('booking_accounting_review_state_conflict')
    if task.object_kind=='booking_receipt_application':
        if application_to_ar_recorded is not True:_fail('booking_accounting_evidence_required',status=422)
        liability=await _fresh_scalar(db, select(BookingAccountingReviewTask).where(
            BookingAccountingReviewTask.tenant_id==tenant_id,BookingAccountingReviewTask.receipt_id==task.receipt_id,
            BookingAccountingReviewTask.object_kind=='booking_receipt_liability').with_for_update())
        if not liability or liability.state!='externally_reconciled':_fail('booking_liability_ack_required')

    receipt=await _fresh_scalar(db, select(BookingReceipt).where(BookingReceipt.tenant_id==tenant_id,BookingReceipt.id==task.receipt_id).with_for_update())
    attempt,appointment,config=await _receipt_source(db,receipt)
    if (task.provider!=attempt.provider or task.provider_account_id!=attempt.provider_account_id
        or task.environment!=attempt.environment or task.configuration_version!=attempt.configuration_version
        or task.qbo_realm_snapshot!=config.qbo_realm_snapshot):_fail('booking_accounting_proof_changed')
    await receipt_balances(db,tenant_id,receipt.id,lock=True)
    name=' '.join(filter(None,[staff.first_name,staff.last_name])) or staff.email
    db.add(BookingAccountingReviewEvent(id=uuid4(),tenant_id=tenant_id,task_id=task.id,
        actor_user_id=staff.id,actor_name_snapshot=name,before_state=task.state,after_state='externally_reconciled',
        receipt_liability_recorded=receipt_liability_recorded,application_to_ar_recorded=application_to_ar_recorded,
        evidence_reference=evidence_reference,external_company_reference=external_company_reference,
        review_note=review_note,idempotency_key=idempotency_key,request_sha256=request_hash))
    task.state='externally_reconciled';task.version+=1
    await db.flush()
    return task


async def mark_manual_accounting_needs_review(db, *, tenant_id, receipt_id, source_event_id, reason):
    """Attach genuine verified provider reconciliation evidence; retain prior ACKs.

    Caller must flush its immutable BookingPaymentEvent and verified receipt/
    appointment updates first, then invoke in the same transaction. No commit.
    """
    from app.db.models.booking_payment import BookingPaymentEvent
    await lock_tenant_financials(db,tenant_id)
    receipt=await _fresh_scalar(db,select(BookingReceipt).where(
        BookingReceipt.tenant_id==tenant_id,BookingReceipt.id==receipt_id).with_for_update())
    event=await _fresh_scalar(db,select(BookingPaymentEvent).where(
        BookingPaymentEvent.tenant_id==tenant_id,BookingPaymentEvent.id==source_event_id))
    if (not receipt or not event or event.appointment_id!=receipt.appointment_id
        or event.attempt_id!=receipt.attempt_id or event.provider!=receipt.provider
        or event.provider_account_id!=receipt.provider_account_id
        or event.source not in {'server_retrieval','verified_connect_webhook'}
        or not event.proof_sha256 or len(event.proof_sha256)!=64
        or not isinstance(reason,str) or not reason.strip()):
        _fail('booking_accounting_review_source_invalid')
    tasks=(await db.scalars(select(BookingAccountingReviewTask).where(
        BookingAccountingReviewTask.tenant_id==tenant_id,
        BookingAccountingReviewTask.receipt_id==receipt_id).order_by(BookingAccountingReviewTask.id)
        .with_for_update().execution_options(populate_existing=True))).all()
    for task in tasks:
        key=f'booking-review-change:{task.id}:{event.id}'
        request_hash=_hash({'task_id':task.id,'event_id':event.id,'proof':event.proof_sha256,'reason':reason})
        existing=await _fresh_scalar(db,select(BookingAccountingReviewEvent).where(
            BookingAccountingReviewEvent.tenant_id==tenant_id,BookingAccountingReviewEvent.idempotency_key==key))
        if existing:
            if existing.request_sha256!=request_hash:_fail('idempotency_conflict')
            continue
        db.add(BookingAccountingReviewEvent(id=uuid4(),tenant_id=tenant_id,task_id=task.id,
            actor_user_id=None,source_event_id=event.id,actor_name_snapshot='Verified provider reconciliation',
            before_state=task.state,after_state='needs_review',receipt_liability_recorded=False,
            application_to_ar_recorded=False,evidence_reference=f'booking-payment-event:{event.id}',
            external_company_reference=task.qbo_realm_snapshot or '',review_note=reason,
            idempotency_key=key,request_sha256=request_hash))
        if task.state!='needs_review':
            task.state='needs_review';task.version+=1
    await db.flush()
    return tasks
