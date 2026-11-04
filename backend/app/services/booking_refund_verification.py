"""Read a known QuickBooks refund; never initiate a provider financial action."""
from decimal import Decimal
from hashlib import sha256
from uuid import uuid4
from fastapi import HTTPException
from sqlalchemy import select
from app.db.models.booking_payment import BookingReceipt,BookingPaymentEvent
from app.db.models.user import User,UserRole
from app.services import booking_payments as booking
from app.services.booking_application_accounting import _receipt_source,mark_manual_accounting_needs_review
from app.services.booking_receipt_application import invalidate_application_settlements,prepayment_view
from app.services.financial_transaction_lock import lock_tenant_financials
from app.services import quickbooks_payments_service as qbp


def refund_event_key(reference):
    return 'qbo-refund:'+sha256(reference.encode()).hexdigest()

async def unresolved_refund_verification(db,tenant_id,appointment_id):
    rows=(await db.scalars(select(BookingPaymentEvent).where(BookingPaymentEvent.tenant_id==tenant_id,BookingPaymentEvent.appointment_id==appointment_id,BookingPaymentEvent.provider_refund_reference.is_not(None)))).all()
    final={row.provider_refund_reference for row in rows if row.provider_event_id==refund_event_key(row.provider_refund_reference)}
    return any(row.provider_refund_reference not in final for row in rows)

async def verification_view(db,apt,reference):
    view=await prepayment_view(db,apt)
    fact=await db.scalar(select(BookingPaymentEvent).where(BookingPaymentEvent.tenant_id==apt.tenant_id,BookingPaymentEvent.appointment_id==apt.id,BookingPaymentEvent.provider_event_id==refund_event_key(reference)))
    state='verified' if fact and fact.verified_refund_delta_minor else 'failed' if fact and fact.after_state=='refund_verification_failed' else 'pending'
    view['refund_verification']={'state':state,'refund_id':reference}
    return view

async def verify_existing_refund(db,actor,identity,body,request_key):
    if actor.role not in {UserRole.GARAGE_OWNER,UserRole.GARAGE_ADMIN}:raise HTTPException(404,'Appointment not found')
    request_key=booking.key(request_key)
    fingerprint=booking.digest({'appointment_id':identity,**body.model_dump()})
    await lock_tenant_financials(db,actor.tenant_id)
    apt=await booking.admitted_appointment(db,actor,identity,write=True)
    replay=await db.scalar(select(BookingPaymentEvent).where(BookingPaymentEvent.tenant_id==actor.tenant_id,BookingPaymentEvent.client_idempotency_key==request_key))
    if replay:
        if replay.appointment_id!=apt.id or replay.request_sha256!=fingerprint:booking.fail('idempotency_conflict','This key belongs to another refund verification.')
        return await verification_view(db,apt,body.refund_id)
    receipt=await db.scalar(select(BookingReceipt).where(BookingReceipt.tenant_id==apt.tenant_id,BookingReceipt.id==apt.confirmed_receipt_id).with_for_update().execution_options(populate_existing=True))
    if not receipt or receipt.provider!='quickbooks_payments':booking.fail('booking_refund_verification_unavailable','This receipt requires its original payment provider for verification.')
    attempt,_,config=await _receipt_source(db,receipt)
    if receipt.version!=body.expected_receipt_version or apt.booking_version!=body.expected_booking_version:booking.fail('booking_application_version_conflict','This reservation changed. Refresh before verifying.')
    reference=body.refund_id
    final_key=refund_event_key(reference)
    existing=await db.scalar(select(BookingPaymentEvent).where(BookingPaymentEvent.provider==attempt.provider,BookingPaymentEvent.provider_account_id==attempt.provider_account_id,BookingPaymentEvent.provider_event_id==final_key))
    if existing and (existing.appointment_id!=apt.id or existing.attempt_id!=attempt.id):booking.fail('booking_refund_identity_mismatch','Refund evidence belongs to another receipt.')
    # No database lifecycle lock is held during provider GETs.
    binding=booking.binding(attempt);expected=booking.metadata(apt,attempt)
    receipt_id=receipt.id;attempt_id=attempt.id;tenant_id=apt.tenant_id
    charge_id=receipt.charge_id
    await db.commit()
    result=None;refund=None;error=None
    try:
        result=await booking.provider.retrieve_booking_payment(db,binding,attempt.provider_intent_id,expected_metadata=expected)
        if (result.charge_id!=charge_id or result.amount_minor!=attempt.amount_minor or result.currency!='usd' or result.environment!=attempt.environment or result.metadata!=expected):
            raise booking.provider.BookingProviderError('Original charge evidence could not be verified.',outcome_unknown=True)
        connection=await booking.provider._connection(db,tenant_id)
        if not booking.provider._healthy_qbo(connection) or connection.realm_id!=config.qbo_realm_snapshot:raise booking.provider.BookingProviderError('Original account is unavailable.',outcome_unknown=True)
        refund=await qbp.get_refund(connection=connection,charge_id=charge_id,refund_id=reference)
        amount=Decimal(str(refund.amount))*100
        if refund.id!=reference or not amount.is_finite() or amount<=0 or amount!=amount.to_integral_value() or amount>attempt.amount_minor:raise qbp.QuickBooksPaymentError('Refund evidence could not be verified.',outcome_unknown=True)
    except (booking.provider.BookingProviderError,qbp.QuickBooksPaymentError) as exc:error=type(exc).__name__
    await db.commit()
    await lock_tenant_financials(db,tenant_id)
    actor=await db.scalar(select(User).where(User.id==actor.id,User.tenant_id==tenant_id,User.is_active.is_(True),User.deleted_at.is_(None),User.role.in_([UserRole.GARAGE_OWNER,UserRole.GARAGE_ADMIN])).with_for_update().execution_options(populate_existing=True))
    if not actor:raise HTTPException(404,'Appointment not found')
    apt=await booking.admitted_appointment(db,actor,identity,write=True)
    receipt=await db.scalar(select(BookingReceipt).where(BookingReceipt.tenant_id==tenant_id,BookingReceipt.id==receipt_id).with_for_update().execution_options(populate_existing=True))
    replay=await db.scalar(select(BookingPaymentEvent).where(BookingPaymentEvent.tenant_id==tenant_id,BookingPaymentEvent.client_idempotency_key==request_key))
    if replay:
        if replay.appointment_id!=apt.id or replay.request_sha256!=fingerprint:booking.fail('idempotency_conflict','This key belongs to another verification.')
        return await verification_view(db,apt,body.refund_id)
    attempt,_,config=await _receipt_source(db,receipt)
    stale=receipt.version!=body.expected_receipt_version or apt.booking_version!=body.expected_booking_version
    final=await db.scalar(select(BookingPaymentEvent).where(BookingPaymentEvent.provider==attempt.provider,BookingPaymentEvent.provider_account_id==attempt.provider_account_id,BookingPaymentEvent.provider_event_id==final_key))
    if final and (final.appointment_id!=apt.id or final.attempt_id!=attempt.id or (refund and final.verified_refund_delta_minor is not None and final.verified_refund_delta_minor!=int(refund.amount*100))):booking.fail('booking_refund_identity_mismatch','Refund evidence does not match the stored receipt.')
    command=BookingPaymentEvent(id=uuid4(),tenant_id=tenant_id,appointment_id=apt.id,attempt_id=attempt_id,actor_user_id=actor.id,source='staff_refund_verification_request',after_state='refund_verification_requested',provider=attempt.provider,provider_account_id=attempt.provider_account_id,provider_event_id='qbo-refund-command:'+booking.digest({'tenant':tenant_id,'key':request_key}),provider_refund_reference=reference,client_idempotency_key=request_key,request_sha256=fingerprint,event_at=booking.now(),proof_sha256=fingerprint)
    db.add(command);await db.flush()
    if final:
        await db.commit();return await verification_view(db,apt,body.refund_id)
    prior=(await db.scalars(select(BookingPaymentEvent).where(BookingPaymentEvent.tenant_id==tenant_id,BookingPaymentEvent.attempt_id==attempt_id,BookingPaymentEvent.provider==attempt.provider,BookingPaymentEvent.provider_account_id==attempt.provider_account_id,BookingPaymentEvent.verified_refund_delta_minor.is_not(None)))).all()
    baseline=sum(row.verified_refund_delta_minor for row in prior if row.provider_refund_reference and row.provider_event_id==refund_event_key(row.provider_refund_reference))
    status=refund.status.casefold() if refund else None
    definitive=not error and status in {'succeeded','completed','captured','refunded','settled'}
    declined=not error and status in {'declined'}
    financial_change=definitive and baseline==receipt.refunded_amount_minor and baseline+int(refund.amount*100)<=receipt.amount_received_minor
    if financial_change or declined:
        delta=int(refund.amount*100) if financial_change else None
        aggregate=baseline+delta if delta else None
        after='refunded' if aggregate==receipt.amount_received_minor else 'refund_pending' if delta else 'refund_verification_failed'
        fact=BookingPaymentEvent(id=uuid4(),tenant_id=tenant_id,appointment_id=apt.id,attempt_id=attempt_id,source='server_retrieval',after_state=after,provider=attempt.provider,provider_account_id=attempt.provider_account_id,provider_event_id=final_key,provider_refund_reference=reference,verified_refund_delta_minor=delta,verified_refund_amount_minor=aggregate,event_at=booking.now(),proof_sha256=booking.digest({'charge_proof':result.proof_digest,'refund':refund.raw,'reference':reference}))
        db.add(fact);await db.flush()
        if declined:
            receipt.version+=1;apt.booking_version+=1
            await db.flush()
        if financial_change:
            receipt.refunded_amount_minor=aggregate;receipt.version+=1
            await db.flush([receipt])
            apt.booking_payment_state=after;apt.booking_version+=1
            await db.flush()
            await mark_manual_accounting_needs_review(db,tenant_id=tenant_id,receipt_id=receipt.id,source_event_id=fact.id,reason='Verified QuickBooks refund changed prepaid liability.')
    else:
        # Accepted/unknown evidence is visible and pauses funding. No invented
        # refund amount, no service lifecycle rewrite, and no second refund.
        observation=None
        if refund is not None and not error:
            proof=booking.digest({'charge_proof':result.proof_digest,'refund':refund.raw,'reference':reference})
            observation_key='qbo-refund-observed:'+proof
            observation=await db.scalar(select(BookingPaymentEvent).where(BookingPaymentEvent.provider==attempt.provider,BookingPaymentEvent.provider_account_id==attempt.provider_account_id,BookingPaymentEvent.provider_event_id==observation_key))
            if observation is None:
                observation=BookingPaymentEvent(id=uuid4(),tenant_id=tenant_id,appointment_id=apt.id,attempt_id=attempt_id,source='server_retrieval',after_state='refund_verification_pending',provider=attempt.provider,provider_account_id=attempt.provider_account_id,provider_event_id=observation_key,provider_refund_reference=reference,event_at=booking.now(),proof_sha256=proof)
                db.add(observation);await db.flush()
        receipt.version+=1;apt.booking_version+=1
        await db.flush()
        if observation:
            await mark_manual_accounting_needs_review(db,tenant_id=tenant_id,receipt_id=receipt.id,source_event_id=observation.id,reason='Known QuickBooks refund verification requires review.')
    await invalidate_application_settlements(db,tenant_id,receipt.id)
    await db.commit()
    view=await prepayment_view(db,apt)
    if stale:
        raise HTTPException(409,{'code':'booking_application_version_conflict','message':'This reservation changed during provider verification. Refresh and verify the existing reference again.','prepayment':view})
    view['refund_verification']={'state':'verified' if financial_change else 'failed' if declined else 'review_required' if stale or (definitive and baseline!=receipt.refunded_amount_minor) else 'pending','refund_id':reference}
    return view
