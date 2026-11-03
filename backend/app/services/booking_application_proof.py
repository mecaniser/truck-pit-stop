"""Read-only proof of the booking portion already included in settlement totals."""
from decimal import Decimal
from sqlalchemy import select
from app.db.models.booking_application import BookingReceiptApplication
from app.db.models.booking_payment import BookingReceipt,BookingPaymentEvent

async def booking_invoice_application_proof(db,invoice,settlement,*,rows=None):
    if rows is None:rows=(await db.scalars(select(BookingReceiptApplication).where(BookingReceiptApplication.tenant_id==invoice.tenant_id,BookingReceiptApplication.invoice_id==invoice.id))).all()
    if not rows:return None,False
    from app.services.booking_refund_verification import unresolved_refund_verification
    from app.services.booking_application_accounting import _receipt_source,receipt_balances
    from app.services.invoice_settlement_service import SettlementDomainError
    total=0
    try:
        if not settlement:return None,True
        for application in rows:
            receipt=await db.scalar(select(BookingReceipt).where(BookingReceipt.tenant_id==invoice.tenant_id,BookingReceipt.id==application.receipt_id).execution_options(populate_existing=True))
            if not receipt:return None,True
            balances=await receipt_balances(db,invoice.tenant_id,receipt.id)
            attempt,apt,config=await _receipt_source(db,receipt)
            if await unresolved_refund_verification(db,invoice.tenant_id,apt.id):return None,True
            evidence=(await db.scalars(select(BookingPaymentEvent).where(BookingPaymentEvent.tenant_id==invoice.tenant_id,BookingPaymentEvent.appointment_id==apt.id,BookingPaymentEvent.attempt_id==attempt.id,BookingPaymentEvent.provider==receipt.provider,BookingPaymentEvent.provider_account_id==receipt.provider_account_id,BookingPaymentEvent.source.in_(['server_retrieval','verified_connect_webhook'])))).all()
            verified=[row for row in evidence if row.proof_sha256 and len(row.proof_sha256)==64]
            if any(row.verified_dispute_amount_minor for row in verified):return None,True
            if receipt.refunded_amount_minor:
                if receipt.provider=='quickbooks_payments':
                    from app.services.booking_refund_verification import refund_event_key
                    deltas=[row for row in verified if row.provider_refund_reference and row.provider_event_id==refund_event_key(row.provider_refund_reference) and row.verified_refund_delta_minor]
                    refund_proven=sum(row.verified_refund_delta_minor for row in deltas)==receipt.refunded_amount_minor and max((row.verified_refund_amount_minor or 0 for row in deltas),default=0)==receipt.refunded_amount_minor
                else:
                    refund_proven=max((row.verified_refund_amount_minor or 0 for row in verified),default=0)==receipt.refunded_amount_minor
                if not refund_proven:return None,True
            if (apt.booking_payment_state not in ({'paid','refund_pending','refunded'} if receipt.refunded_amount_minor else {'paid'}) or apt.repair_order_id!=invoice.repair_order_id or application.repair_order_id!=invoice.repair_order_id
                or application.customer_id!=settlement.customer_id or application.customer_id!=(invoice.billed_customer_id or apt.customer_id)
                or application.settlement_id!=settlement.id or application.receipt_proof_sha256!=receipt.proof_sha256
                or application.provider!=attempt.provider or application.provider_account_id!=attempt.provider_account_id
                or application.configuration_version!=attempt.configuration_version or application.environment!=attempt.environment
                or application.qbo_realm_snapshot!=config.qbo_realm_snapshot):return None,True
            total+=application.amount_minor
        if Decimal(total)/100>Decimal(str(settlement.confirmed_principal)):return None,True
    except SettlementDomainError:
        return None,True
    return f'{Decimal(total)/100:.2f}',False
