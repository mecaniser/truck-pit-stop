"""Shared serialization boundary for invoice export and local cash acceptance."""
from sqlalchemy import inspect, select, or_, and_
from sqlalchemy.ext.asyncio import async_object_session
from app.db.models.invoice import Invoice

LOCAL_CASH = "local_cash_only"
LOCAL_CASH_SYNC = "not_applicable_local_cash"
HISTORICAL_HOLD = "historical_export_hold"
AWAITING_PAYMENT = "awaiting_payment"


async def mark_awaiting_payment(db, invoice):
    """Change presentation without laundering orphan historical export evidence."""
    from app.db.models.provider_outbox import ProviderOutboxEvent
    from app.services.provider_outbox_service import EMAIL_NOTIFICATION_EVENT
    if invoice.quickbooks_sync_status not in {None, "pending", "not_synced", "not_required", AWAITING_PAYMENT}:
        history = await db.scalar(select(ProviderOutboxEvent.id).where(
            ProviderOutboxEvent.tenant_id == invoice.tenant_id,
            ProviderOutboxEvent.aggregate_id == invoice.id,
            ProviderOutboxEvent.event_type != EMAIL_NOTIFICATION_EVENT,
        ).limit(1))
        if history is None:
            invoice.cash_export_review_required = True
    invoice.quickbooks_sync_status = AWAITING_PAYMENT


async def first_export_awaits_payment(db, invoice):
    """Pilot invoices become QBO receivables after the first real noncash receipt.

    Existing QBO links and nonpilot shops keep their original export timing.
    Invoice PAID status alone is not proof of a payment (historical baselines).
    Caller holds the shared policy lock before using this dispatch decision.
    """
    from app.core.config import settings
    from app.db.models.tenant import Tenant
    from app.db.models.invoice_settlement import InvoicePaymentAttempt
    from app.db.models.payment import Payment, PaymentMethod, PaymentStatus
    if not settings.INVOICE_SPLIT_PAYMENTS_ENABLED:
        return False
    linked = await db.scalar(select(Invoice.quickbooks_invoice_id).where(
        Invoice.id == invoice.id, Invoice.tenant_id == invoice.tenant_id))
    if linked:
        return False
    enabled = await db.scalar(select(Tenant.invoice_split_payments_enabled).where(
        Tenant.id == invoice.tenant_id))
    if not enabled:
        return False
    receipt = await db.scalar(select(InvoicePaymentAttempt.id).where(
        InvoicePaymentAttempt.tenant_id == invoice.tenant_id,
        InvoicePaymentAttempt.invoice_id == invoice.id,
        InvoicePaymentAttempt.rail.in_(["card", "zelle", "check", "ach"]),
        or_(InvoicePaymentAttempt.state == "confirmed", and_(
            InvoicePaymentAttempt.state.in_(["refunded", "reversed"]),
            InvoicePaymentAttempt.confirmed_at.is_not(None))),
        InvoicePaymentAttempt.applied_principal_amount > 0,
        InvoicePaymentAttempt.deleted_at.is_(None),
    ).limit(1))
    if receipt is not None:
        return False
    legacy_receipt = await db.scalar(select(Payment.id).where(
        Payment.tenant_id == invoice.tenant_id, Payment.invoice_id == invoice.id,
        Payment.status == PaymentStatus.COMPLETED, Payment.amount > 0,
        Payment.deleted_at.is_(None),
        Payment.method.in_([PaymentMethod.STRIPE, PaymentMethod.QUICKBOOKS,
                           PaymentMethod.ZELLE, PaymentMethod.CHECK, PaymentMethod.ACH,
                           PaymentMethod.FLEET_PAYMENT]),
    ).limit(1))
    return legacy_receipt is None


async def locked_policy(db, invoice, *, nowait=True):
    # Scalar read deliberately bypasses an already-loaded ORM identity. Lock is
    # retained until caller commit, including all remote dispatch/read-back IO.
    from app.db.models.invoice_settlement import InvoiceSettlement
    try:
        await db.scalar(select(InvoiceSettlement.id).where(
            InvoiceSettlement.invoice_id == invoice.id,
            InvoiceSettlement.tenant_id == invoice.tenant_id,
        ).with_for_update(nowait=nowait))
        policy = await db.scalar(select(Invoice.accounting_policy).where(
            Invoice.id == invoice.id, Invoice.tenant_id == invoice.tenant_id,
        ).with_for_update(nowait=nowait))
    except Exception as exc:
        if nowait and getattr(getattr(exc, "orig", None), "sqlstate", None) == "55P03":
            from app.services.invoice_settlement_service import SettlementDomainError
            raise SettlementDomainError("invoice_busy", "Invoice processing is in progress. Refresh and retry.", retryable=True) from exc
        raise
    return policy or "standard"


async def require_exportable_invoice(invoice):
    from app.services.quickbooks_accounting_service import QuickBooksAccountingError
    db = async_object_session(invoice) if inspect(invoice, raiseerr=False) is not None else None
    policy = await locked_policy(db, invoice) if db else getattr(invoice, "accounting_policy", "standard")
    if policy == LOCAL_CASH:
        raise QuickBooksAccountingError("Local cash invoices are excluded from QuickBooks")
    from app.services.new_receipt_accounting import scoped_invoice
    if policy == HISTORICAL_HOLD and not scoped_invoice(invoice):
        raise QuickBooksAccountingError("Historical invoice export is held for individual review")
    if db and await first_export_awaits_payment(db, invoice):
        raise QuickBooksAccountingError("Invoice export awaits a confirmed noncash payment")


async def require_standard_payment(db, invoice, *, verified_provider_fact=False, new_entry=False, attempt=None):
    from app.services.invoice_settlement_service import SettlementDomainError
    policy = await locked_policy(db, invoice)
    if policy == HISTORICAL_HOLD and not verified_provider_fact:
        from app.services.new_receipt_accounting import require_clean_historical_balance, valid_attempt_authorization
        if new_entry:
            await require_clean_historical_balance(db, invoice)
        elif attempt is None or attempt.invoice_id != invoice.id or attempt.tenant_id != invoice.tenant_id or not await valid_attempt_authorization(db, attempt, check_connection=True):
            raise SettlementDomainError("historical_export_hold", "This historical payment requires individual accounting review.")
    if policy == LOCAL_CASH:
        raise SettlementDomainError("local_cash_only", "This invoice is cash-only and cannot use this payment action.")
