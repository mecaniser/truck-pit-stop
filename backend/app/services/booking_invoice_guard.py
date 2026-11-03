"""Prevent collecting an exact linked repair order twice against booking funds.

This is an admission guard only: receipts remain prepaid liabilities, with no
invented invoice Payment, credit application, or accounting export.
"""
from sqlalchemy import and_, select

from app.db.models.appointment import Appointment
from app.db.models.booking_payment import BookingPaymentAttempt, BookingReceipt
from app.db.models.repair_order import RepairOrder
from app.services.financial_transaction_lock import lock_tenant_financials


async def require_booking_prepayment_resolved(db, tenant_id, repair_order_id):
    if repair_order_id is None:
        return
    await lock_tenant_financials(db, tenant_id)
    # Only the in-process atomic writer can install this exact transaction scope.
    scope = getattr(db,'info',{}).get('_booking_invoice_application_scope')
    if scope is not None and scope.matches(db, tenant_id, repair_order_id):
        return
    # Include deleted/cancelled appointments and ledger rows: deleting a record
    # or releasing capacity does not dispose of captured money.
    appointments = (await db.scalars(select(Appointment.id).join(
        RepairOrder, and_(RepairOrder.id == Appointment.repair_order_id,
                          RepairOrder.tenant_id == Appointment.tenant_id)
    ).where(Appointment.tenant_id == tenant_id,
            RepairOrder.tenant_id == tenant_id,
            RepairOrder.id == repair_order_id))).all()
    if not appointments:
        return
    from app.services.booking_refund_verification import unresolved_refund_verification
    for appointment_id in appointments:
        if await unresolved_refund_verification(db,tenant_id,appointment_id):
            from app.services.invoice_settlement_service import SettlementDomainError
            raise SettlementDomainError('booking_refund_verification_pending','Existing booking refund verification must be resolved before another collection.')
    attempts = (await db.scalars(select(BookingPaymentAttempt).where(
        BookingPaymentAttempt.tenant_id == tenant_id,
        BookingPaymentAttempt.appointment_id.in_(appointments)))).all()
    receipts = (await db.scalars(select(BookingReceipt).where(
        BookingReceipt.tenant_id == tenant_id,
        BookingReceipt.appointment_id.in_(appointments)))).all()
    by_attempt = {row.id: row for row in attempts}
    resolved = set()
    blocked = False
    for receipt in receipts:
        attempt = by_attempt.get(receipt.attempt_id)
        valid = (attempt is not None and attempt.appointment_id == receipt.appointment_id
                 and attempt.provider == receipt.provider
                 and attempt.provider_account_id == receipt.provider_account_id
                 and attempt.provider_intent_id == receipt.provider_intent_id
                 and receipt.currency == attempt.currency == 'usd'
                 and receipt.amount_received_minor == attempt.amount_minor
                 and receipt.proof_sha256 and receipt.verification_basis
                 and attempt.state == 'succeeded' and attempt.verified_at is not None
                 and 0 <= receipt.refunded_amount_minor <= receipt.amount_received_minor)
        applied=0
        if valid:
            from app.db.models.booking_application import BookingReceiptApplication
            from app.db.models.invoice import Invoice
            from app.db.models.invoice_settlement import InvoiceSettlement
            from app.services.booking_application_proof import booking_invoice_application_proof
            applications=(await db.scalars(select(BookingReceiptApplication).where(BookingReceiptApplication.tenant_id==tenant_id,BookingReceiptApplication.receipt_id==receipt.id))).all()
            for application in applications:
                invoice=await db.get(Invoice,application.invoice_id)
                settlement=await db.get(InvoiceSettlement,application.settlement_id)
                proof,review=await booking_invoice_application_proof(db,invoice,settlement)
                if review or proof is None:
                    valid=False;break
                applied+=application.amount_minor
        if not valid or receipt.amount_received_minor != receipt.refunded_amount_minor+applied:
            blocked = True
        else:
            resolved.add(receipt.attempt_id)
    for attempt in attempts:
        # Only explicit terminal no-funds evidence, or a fully refunded verified
        # receipt, releases admission. Unknown future states fail closed.
        if attempt.state not in {'failed', 'cancelled'} and attempt.id not in resolved:
            blocked = True
    if blocked:
        from app.services.invoice_settlement_service import SettlementDomainError
        raise SettlementDomainError(
            'booking_prepayment_review_required',
            'This repair order has booking payment funds or payment verification pending. '
            'Review and apply or verify refund of the prepayment before invoicing or collecting again.',
        )
