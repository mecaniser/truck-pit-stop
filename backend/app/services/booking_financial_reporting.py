"""Read-only booking cash/liability disclosure, separate from sale revenue.

Receipt periods use provider received_at. Refund amounts are the CURRENT refund
aggregate for that receipt cohort, not an invented refund-period cash flow.
Applications use ledger created_at and represent zero additional cash received.
"""
from datetime import datetime, timezone
from decimal import Decimal
from typing import Literal, Optional
from pydantic import BaseModel
from sqlalchemy import select, func, case, and_, exists
from app.db.models.booking_payment import BookingReceipt, BookingPaymentAttempt
from app.db.models.booking_application import BookingReceiptApplication, BookingAccountingReviewTask
from app.db.models.appointment import Appointment
from app.db.models.invoice_settlement import TenantPaymentProviderConfiguration


class BookingPrepaymentsReport(BaseModel):
    currency: Literal['USD']='USD'
    classification: Literal['prepaid_liability']='prepaid_liability'
    period_start_at: datetime
    period_end_at: datetime
    as_of: datetime
    period_receipt_count: int
    period_received_gross: str
    period_received_refunded_to_date: str
    period_application_count: int
    period_applied_to_invoices: str
    current_unapplied_liability: Optional[str]
    reconciliation_required_count: int
    unverified_receipt_count: int
    period_unverified_receipt_gross: str
    note: str


def _money(minor):
    return f'{Decimal(minor or 0)/100:.2f}'


async def booking_prepayments_for_period(db,tenant_id,period_start,period_end,*,as_of=None):
    as_of=as_of or datetime.now(timezone.utc)
    if not period_start.tzinfo or not period_end.tzinfo or not as_of.tzinfo or period_start>=period_end:
        raise ValueError('Booking report requires a timezone-aware half-open interval')
    applications=select(BookingReceiptApplication.receipt_id.label('receipt_id'),
        func.sum(BookingReceiptApplication.amount_minor).label('applied')).where(
        BookingReceiptApplication.tenant_id==tenant_id).group_by(BookingReceiptApplication.receipt_id).subquery()
    valid=and_(BookingPaymentAttempt.id.is_not(None),Appointment.id.is_not(None),
        TenantPaymentProviderConfiguration.id.is_not(None),BookingPaymentAttempt.state=='succeeded',
        BookingPaymentAttempt.verified_at.is_not(None),func.length(BookingReceipt.proof_sha256)==64,
        BookingReceipt.verification_basis.in_(['server_retrieval','verified_connect_webhook']),
        BookingReceipt.currency=='usd',BookingPaymentAttempt.currency=='usd',
        BookingReceipt.provider==BookingPaymentAttempt.provider,
        BookingReceipt.provider_account_id==BookingPaymentAttempt.provider_account_id,
        BookingReceipt.provider_intent_id==BookingPaymentAttempt.provider_intent_id,
        BookingReceipt.charge_id.is_not(None),func.length(BookingReceipt.charge_id)>0,
        BookingPaymentAttempt.provider_charge_id.is_not(None),func.length(BookingPaymentAttempt.provider_charge_id)>0,
        BookingReceipt.charge_id==BookingPaymentAttempt.provider_charge_id,
        BookingReceipt.amount_received_minor==BookingPaymentAttempt.amount_minor,
        BookingPaymentAttempt.provider==TenantPaymentProviderConfiguration.selected_provider,
        BookingPaymentAttempt.provider_account_id==TenantPaymentProviderConfiguration.provider_account_snapshot,
        Appointment.customer_id==BookingPaymentAttempt.customer_id,
        Appointment.booking_provider_configuration_version==BookingPaymentAttempt.configuration_version,
        Appointment.booking_provider_environment==BookingPaymentAttempt.environment,
        BookingReceipt.received_at<=as_of)
    # coalesce ensures malformed/absent provenance is counted as unverified.
    valid=func.coalesce(valid,False)
    in_period=and_(BookingReceipt.received_at>=period_start,BookingReceipt.received_at<period_end)
    balance=BookingReceipt.amount_received_minor-BookingReceipt.refunded_amount_minor-func.coalesce(applications.c.applied,0)
    pending_review=exists(select(BookingAccountingReviewTask.id).where(
        BookingAccountingReviewTask.tenant_id==tenant_id,
        BookingAccountingReviewTask.receipt_id==BookingReceipt.id,
        BookingAccountingReviewTask.state!='externally_reconciled'))
    def total(condition,amount=1):return func.coalesce(func.sum(case((condition,amount),else_=0)),0)
    row=(await db.execute(select(
        total(and_(valid,in_period)).label('receipt_count'),
        total(and_(valid,in_period),BookingReceipt.amount_received_minor).label('gross'),
        total(and_(valid,in_period),BookingReceipt.refunded_amount_minor).label('refunds'),
        total(~valid).label('unverified'),
        total(and_(~valid,in_period),BookingReceipt.amount_received_minor).label('unverified_gross'),
        total(and_(valid,balance>=0),balance).label('liability'),
        total(and_(valid,balance<0)).label('overdrawn'),
        total((~valid)|(balance<0)|pending_review|Appointment.booking_payment_state.in_(['payment_processing','payment_received_review','refund_pending'])).label('review_count'),
    ).select_from(BookingReceipt).outerjoin(BookingPaymentAttempt,and_(
        BookingPaymentAttempt.tenant_id==BookingReceipt.tenant_id,
        BookingPaymentAttempt.id==BookingReceipt.attempt_id,
        BookingPaymentAttempt.appointment_id==BookingReceipt.appointment_id)).outerjoin(Appointment,and_(
        Appointment.tenant_id==BookingReceipt.tenant_id,Appointment.id==BookingReceipt.appointment_id))
        .outerjoin(TenantPaymentProviderConfiguration,and_(
            TenantPaymentProviderConfiguration.tenant_id==BookingReceipt.tenant_id,
            TenantPaymentProviderConfiguration.version==BookingPaymentAttempt.configuration_version))
        .outerjoin(applications,applications.c.receipt_id==BookingReceipt.id)
        .where(BookingReceipt.tenant_id==tenant_id))).one()
    applied=(await db.execute(select(func.count(BookingReceiptApplication.id),
        func.coalesce(func.sum(BookingReceiptApplication.amount_minor),0)).where(
        BookingReceiptApplication.tenant_id==tenant_id,BookingReceiptApplication.created_at>=period_start,
        BookingReceiptApplication.created_at<period_end))).one()
    return BookingPrepaymentsReport(period_start_at=period_start,period_end_at=period_end,as_of=as_of,
        period_receipt_count=int(row.receipt_count),period_received_gross=_money(row.gross),
        period_received_refunded_to_date=_money(row.refunds),period_application_count=int(applied[0]),
        period_applied_to_invoices=_money(applied[1]),
        current_unapplied_liability=None if row.unverified or row.overdrawn else _money(row.liability),
        reconciliation_required_count=int(row.review_count),unverified_receipt_count=int(row.unverified),
        period_unverified_receipt_gross=_money(row.unverified_gross),
        note='Booking receipts are prepaid liabilities, separate from invoice revenue. Receipt totals use provider received time; refunds are current cumulative refunds for receipts received in this period. Applications use their posting time and add no new cash. Unapplied liability is current across all periods; unavailable amounts require reconciliation.')
