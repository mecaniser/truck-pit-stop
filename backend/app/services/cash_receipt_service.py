"""Read-only, fail-closed customer receipt amounts backed by cash evidence."""
from datetime import datetime
from decimal import Decimal
from typing import Literal
from pydantic import BaseModel
from sqlalchemy import select
from app.db.models.payment import Payment
from app.db.models.invoice_settlement import InvoiceSettlement, InvoicePaymentAttempt

ZERO = Decimal('0.00')
def money(value):
    return Decimal(str(value or 0)).quantize(Decimal('0.01'))
def value(value):
    return getattr(value, 'value', value)

class CashReceipt(BaseModel):
    method: Literal['cash'] = 'cash'
    amount: Decimal
    subtotal: Decimal
    shop_supplies_amount: Decimal
    service_fee_amount: Decimal = ZERO
    tax_amount: Decimal
    discount_amount: Decimal
    paid_at: datetime


def project_cash_receipt(invoice, payments, settlement=None, attempts=()):
    if value(invoice.status) != 'paid' or len(payments) != 1:
        return None
    payment = payments[0]
    if (payment.tenant_id != invoice.tenant_id or payment.invoice_id != invoice.id
        or value(payment.status) != 'completed' or value(payment.method) != 'cash'
        or getattr(payment, 'deleted_at', None) is not None
        or money(getattr(payment, 'quickbooks_refunded_amount', 0)) != ZERO):
        return None
    amount = money(payment.amount)
    subtotal, supplies, discount = (money(getattr(invoice, key)) for key in ('subtotal','shop_supplies_amount','discount_amount'))
    base = subtotal + supplies - discount
    tax = ZERO
    paid_at = invoice.paid_at or payment.created_at
    linked_id = getattr(payment, 'invoice_payment_attempt_id', None)
    if linked_id:
        if settlement is None or len(attempts) != 1:
            return None
        attempt = attempts[0]
        if (attempt.id != linked_id or attempt.tenant_id != invoice.tenant_id
            or attempt.invoice_id != invoice.id or attempt.settlement_id != settlement.id
            or attempt.payment_id != payment.id or attempt.state != 'confirmed' or attempt.rail != 'cash'
            or settlement.tenant_id != invoice.tenant_id or settlement.invoice_id != invoice.id
            or settlement.state != 'paid'):
            return None
        if any(money(getattr(attempt, key)) != ZERO for key in ('card_fee_amount','card_fee_tax_amount','applied_card_fee_amount','applied_card_fee_tax_amount','unapplied_amount')):
            return None
        if any(money(getattr(settlement, key)) != ZERO for key in ('active_pending_principal','unapplied_credit','refund_pending')):
            return None
        if any(money(n) != amount for n in (attempt.received_amount, attempt.applied_principal_amount, settlement.confirmed_principal, settlement.principal_total)):
            return None
        tax = money(invoice.tax_amount) - money(settlement.max_card_fee_tax)
        paid_at = attempt.confirmed_at
    elif attempts:
        return None
    if amount <= ZERO or tax < ZERO or base + tax != amount or paid_at is None:
        return None
    return CashReceipt(amount=amount, subtotal=subtotal, shop_supplies_amount=supplies,
                       tax_amount=tax, discount_amount=discount, paid_at=paid_at)


async def load_cash_receipt(db, invoice):
    if value(invoice.status) != 'paid':
        return None
    payments = (await db.execute(select(Payment).where(
        Payment.tenant_id == invoice.tenant_id, Payment.invoice_id == invoice.id,
    ))).scalars().all()
    attempts = (await db.execute(select(InvoicePaymentAttempt).where(
        InvoicePaymentAttempt.tenant_id == invoice.tenant_id,
        InvoicePaymentAttempt.invoice_id == invoice.id,
    ))).scalars().all()
    settlement = None
    if any(getattr(p, 'invoice_payment_attempt_id', None) for p in payments):
        settlement = (await db.execute(select(InvoiceSettlement).where(
            InvoiceSettlement.tenant_id == invoice.tenant_id,
            InvoiceSettlement.invoice_id == invoice.id,
        ))).scalar_one_or_none()
    return project_cash_receipt(invoice, payments, settlement, attempts)


def receipt_invoice_view(invoice, receipt):
    """Overlay presentation values without mutating the mapped financial record."""
    class View:
        def __getattr__(self, name):
            if name == 'total_amount':
                return receipt.amount
            if name in receipt.model_fields:
                return getattr(receipt, name)
            return getattr(invoice, name)
    return View()
