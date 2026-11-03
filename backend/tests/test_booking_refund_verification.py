from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4
from unittest.mock import AsyncMock
import pytest
from sqlalchemy import select,func
from fastapi import HTTPException
from app.db.models.booking_payment import BookingReceipt,BookingPaymentAttempt,BookingPaymentEvent
from app.api.v1.endpoints.appointments import BookingRefundVerificationBody
from app.services import booking_payments as booking
from app.services.booking_refund_verification import verify_existing_refund,unresolved_refund_verification
from app.services.booking_payment_provider import BookingProviderError
from test_booking_fulfillment import staff_user,paid
from test_verified_booking_flow import setup_booking,result

async def context(db,setup,staff,monkeypatch,*,status='SETTLED',refund_id='opaque/provider?refund'):
    apt=await paid(db,setup,monkeypatch)
    attempt=await db.scalar(select(BookingPaymentAttempt))
    import app.services.booking_refund_verification as verification
    monkeypatch.setattr(booking.provider,'retrieve_booking_payment',AsyncMock(return_value=result(apt,attempt,provider_id=attempt.provider_intent_id)))
    monkeypatch.setattr(booking.provider,'_connection',AsyncMock(return_value=SimpleNamespace(realm_id='realm-fixture')))
    monkeypatch.setattr(booking.provider,'_healthy_qbo',lambda connection:True)
    getter=AsyncMock(return_value=SimpleNamespace(id=refund_id,status=status,amount=Decimal('25.00'),raw={'id':refund_id,'status':status,'amount':'25.00'}))
    monkeypatch.setattr(verification.qbp,'get_refund',getter)
    create=AsyncMock();refund=AsyncMock()
    monkeypatch.setattr(verification.qbp,'create_charge',create);monkeypatch.setattr(verification.qbp,'refund_charge',refund)
    return apt,getter,create,refund

@pytest.mark.asyncio
async def test_known_qbo_refund_get_only_no_bank_claim_duplicate_reference_applies_once(db_session,setup_booking,staff_user,monkeypatch):
    apt,getter,create,refund=await context(db_session,setup_booking,staff_user,monkeypatch)
    body=BookingRefundVerificationBody(refund_id='opaque/provider?refund',expected_receipt_version=1,expected_booking_version=apt.booking_version)
    response=await verify_existing_refund(db_session,staff_user,apt.id,body,'verify-refund-once')
    receipt=await db_session.scalar(select(BookingReceipt))
    assert receipt.refunded_amount_minor==2500 and apt.status.value=='confirmed'
    assert response['refund_verification']['state']=='verified'
    assert not await unresolved_refund_verification(db_session,apt.tenant_id,apt.id)
    replay=await verify_existing_refund(db_session,staff_user,apt.id,body,'verify-refund-once')
    getter.assert_awaited_once();create.assert_not_awaited();refund.assert_not_awaited()
    with pytest.raises(HTTPException) as denied:await verify_existing_refund(db_session,staff_user,apt.id,body.model_copy(update={'refund_id':'another'}),'verify-refund-once')
    assert denied.value.detail['code']=='idempotency_conflict'
    identity=apt.id
    await db_session.rollback()
    await db_session.refresh(staff_user)
    receipt=await db_session.scalar(select(BookingReceipt));apt=await db_session.get(booking.Appointment,identity)
    fresh=body.model_copy(update={'expected_receipt_version':receipt.version,'expected_booking_version':apt.booking_version})
    await verify_existing_refund(db_session,staff_user,apt.id,fresh,'verify-same-id-again')
    assert receipt.refunded_amount_minor==2500
    assert await db_session.scalar(select(func.sum(BookingPaymentEvent.verified_refund_delta_minor)))==2500

@pytest.mark.asyncio
@pytest.mark.parametrize('observation',['ISSUED','UNRECOGNIZED','read_failure'])
async def test_pending_or_failed_read_never_claims_refund_and_pauses_funding(db_session,setup_booking,staff_user,monkeypatch,observation):
    apt,getter,create,refund=await context(db_session,setup_booking,staff_user,monkeypatch,status=observation)
    if observation=='read_failure':getter.side_effect=booking.provider.qbp.QuickBooksPaymentError('unavailable',outcome_unknown=True)
    response=await verify_existing_refund(db_session,staff_user,apt.id,BookingRefundVerificationBody(refund_id='opaque/provider?refund',expected_receipt_version=1,expected_booking_version=apt.booking_version),'pending-qbo-refund')
    receipt=await db_session.scalar(select(BookingReceipt))
    assert receipt.refunded_amount_minor==0 and apt.status.value=='confirmed'
    assert response['refund_verification']['state']=='pending' and response['refund_verification_pending']
    assert not response['can_apply']
    assert (await booking.snapshot(db_session,apt))['booking_payment_state']=='refund_pending'
    create.assert_not_awaited();refund.assert_not_awaited()
