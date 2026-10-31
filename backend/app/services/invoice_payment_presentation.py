"""Read-only, tenant-scoped payment facts for customer invoice copies."""
from decimal import Decimal, InvalidOperation
from typing import Optional
from pydantic import BaseModel
from sqlalchemy import select
from app.db.models.invoice_settlement import InvoiceSettlement
from app.db.models.payment import Payment

ZERO = Decimal('0.00')

def value(v):
    return getattr(v, 'value', v)

def money(v):
    n = Decimal(str(v)).quantize(Decimal('0.01'))
    if not n.is_finite() or n < ZERO:
        raise ValueError('Invalid monetary evidence')
    return n

class InvoicePaymentSummary(BaseModel):
    state: str  # paid, unpaid, partially_paid, payment_pending, partially_paid_pending, overdue, cancelled, unknown
    applied_amount: Optional[str] = None
    balance_due: Optional[str] = None
    pending_amount: Optional[str] = None
    note: Optional[str] = None
    basis: str = 'unknown'  # settlement, cash_receipt, legacy_payments, status_only, cancelled, unknown


def project_payment_summary(invoice, settlement=None, payments=(), cash_receipt=None):
    status = value(invoice.status)
    if status == 'cancelled':
        return InvoicePaymentSummary(state='cancelled', basis='cancelled', note='Cancelled invoice. No payment requested.')
    def unknown():
        return InvoicePaymentSummary(state='unknown', note='Current balance needs shop verification. Contact the shop before paying.')
    try:
        if cash_receipt:
            return InvoicePaymentSummary(state='paid', applied_amount=f'{money(cash_receipt.amount):.2f}', balance_due='0.00', basis='cash_receipt')
        if settlement is not None:
            if (settlement.invoice_id != invoice.id or settlement.tenant_id != invoice.tenant_id
                or getattr(settlement, 'deleted_at', None) is not None
                or getattr(settlement, 'currency', 'USD') != 'USD'
                or getattr(settlement, 'legacy_reconciliation_status', 'native') not in ('native', 'reconciled', 'legacy_paid_snapshot', 'legacy_paid_without_tender')):
                return unknown()
            total, applied, pending = (money(getattr(settlement,k)) for k in ('principal_total','confirmed_principal','active_pending_principal'))
            balance = max(ZERO, total-applied)
            state = 'paid' if balance == ZERO else ('partially_paid_pending' if applied and pending else 'partially_paid' if applied else 'payment_pending' if pending else 'overdue' if status=='overdue' else 'unpaid')
            notes = []
            if money(getattr(settlement,'max_card_fee',0)) or money(getattr(settlement,'max_card_fee_tax',0)):
                notes.append('Amounts applied and balance exclude processing fees; final payment quote shows applicable card fees.')
            if pending:
                notes.append('Pending payment is awaiting confirmation and has not reduced the balance.')
            if money(getattr(settlement,'refund_pending',0)):
                notes.append('A refund is pending; contact the shop for its status.')
            if money(getattr(settlement,'unapplied_credit',0)):
                notes.append('Unapplied funds are held separately from this invoice balance.')
            # A paid baseline records settlement, not reconstructed payments or credit tender.
            known_applied = None if getattr(settlement,'legacy_reconciliation_status','native') in ('legacy_paid_snapshot','legacy_paid_without_tender') else f'{applied:.2f}'
            return InvoicePaymentSummary(state=state, applied_amount=known_applied, balance_due=f'{balance:.2f}', pending_amount=f'{pending:.2f}' if pending else None, note=' '.join(notes) or None, basis='settlement')
        valid = []
        for p in payments:
            if p.invoice_id != invoice.id or p.tenant_id != invoice.tenant_id:
                return unknown()
            if getattr(p,'deleted_at',None) is not None:
                continue
            if (getattr(p,'invoice_payment_attempt_id',None) or value(p.status)=='refunded'
                or money(getattr(p,'quickbooks_refunded_amount',0) or 0)):
                return unknown()  # cannot map refunded gross tender to principal without its settlement
            valid.append(p)
        total = money(invoice.total_amount)
        applied = sum((money(p.amount) for p in valid if value(p.status)=='completed'), ZERO)
        pending = sum((money(p.amount) for p in valid if value(p.status)=='pending'), ZERO)
        if applied > total:
            return unknown()
        if status in ('partially_paid', 'partial') and not valid:
            return unknown()
        if status == 'paid' and not valid:
            return InvoicePaymentSummary(state='paid', balance_due='0.00', basis='status_only', note='Invoice marked paid; payment breakdown is not available on this copy.')
        if status == 'paid' and applied != total:
            return unknown()
        balance=max(ZERO,total-applied)
        pending_reported = pending or bool(getattr(invoice,'pending_zelle_confirmation',False))
        state='paid' if balance==ZERO else 'partially_paid_pending' if applied and pending_reported else 'partially_paid' if applied else 'payment_pending' if pending_reported else 'overdue' if status=='overdue' else 'unpaid'
        return InvoicePaymentSummary(state=state, applied_amount=f'{applied:.2f}',balance_due=f'{balance:.2f}',pending_amount=f'{pending:.2f}' if pending else None,basis='legacy_payments',note='Pending payment is awaiting confirmation and has not reduced the balance.' if pending_reported else None)
    except (InvalidOperation, ValueError, TypeError, AttributeError):
        return unknown()


async def load_payment_summary(db, invoice, cash_receipt=None):
    if cash_receipt or db is None:
        return project_payment_summary(invoice, cash_receipt=cash_receipt)
    settlement=(await db.execute(select(InvoiceSettlement).where(
        InvoiceSettlement.tenant_id==invoice.tenant_id, InvoiceSettlement.invoice_id==invoice.id,
        InvoiceSettlement.deleted_at.is_(None),
    ))).scalar_one_or_none()
    payments=[]
    if settlement is None:
        payments=(await db.execute(select(Payment).where(
            Payment.tenant_id==invoice.tenant_id,Payment.invoice_id==invoice.id,
            Payment.deleted_at.is_(None),
        ))).scalars().all()
    return project_payment_summary(invoice, settlement, payments, cash_receipt)


def payment_summary_html(summary):
    from html import escape
    labels = {'paid':'PAID','unpaid':'UNPAID','partially_paid':'PARTIALLY PAID','payment_pending':'PAYMENT PENDING','partially_paid_pending':'PARTIALLY PAID · PAYMENT PENDING','overdue':'OVERDUE','cancelled':'CANCELLED','unknown':'BALANCE NEEDS VERIFICATION'}
    rows = [f'<p><strong>{labels.get(summary.state, "BALANCE NEEDS VERIFICATION")}</strong></p>']
    if summary.applied_amount is not None:
        label = 'Cash received' if summary.basis == 'cash_receipt' else 'Payments / credits applied'
        rows.append(f'<p>{label}: ${Decimal(summary.applied_amount):,.2f}</p>')
    if summary.pending_amount is not None:
        rows.append(f'<p>Awaiting confirmation: ${Decimal(summary.pending_amount):,.2f}</p>')
    if summary.balance_due is not None:
        rows.append(f'<p><strong>Balance due: ${Decimal(summary.balance_due):,.2f}</strong></p>')
    if summary.note:
        rows.append(f'<p>{escape(summary.note)}</p>')
    return '<div style="padding:12px 28px;background:#f3f4f6;">' + ''.join(rows) + '</div>'
