"""Shared serialization boundary for invoice export and local cash acceptance."""
from sqlalchemy import inspect, select
from sqlalchemy.ext.asyncio import async_object_session
from app.db.models.invoice import Invoice

LOCAL_CASH = "local_cash_only"
LOCAL_CASH_SYNC = "not_applicable_local_cash"


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


async def require_standard_payment(db, invoice):
    from app.services.invoice_settlement_service import SettlementDomainError
    if await locked_policy(db, invoice) == LOCAL_CASH:
        raise SettlementDomainError("local_cash_only", "This invoice is cash-only and cannot use this payment action.")
