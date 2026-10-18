"""Bounded, tenant-scoped source loader for DB-135 receivable attestations.

This is a read-only evidence loader, not an eligibility decision or apply path.
The calling transaction must be repeatable-read; production reads must also be
read-only. A future apply path must acquire the tenant financial lock separately.
"""
from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.customer import Customer
from app.db.models.invoice import Invoice
from app.db.models.invoice_settlement import (
    CustomerCreditEntry, InvoicePaymentAttempt, InvoicePaymentLedgerEvent,
    InvoiceSettlement, PaymentOverpayment, PaymentProviderDispute, PaymentRefund,
)
from app.db.models.payment import Payment
from app.db.models.repair_order import RepairOrder
from app.services.receivable_attestation_fingerprint import (
    MAX_SOURCE_ROWS_PER_KIND, fingerprint_source_bundle,
)


@dataclass(frozen=True)
class ReceivableSourceBundle:
    invoice: Invoice
    order: RepairOrder
    customer: Customer
    linked_rows: dict[str, list[object]]
    fingerprint: str


async def _bounded(db: AsyncSession, statement) -> list[object]:
    rows = list((await db.execute(statement.limit(MAX_SOURCE_ROWS_PER_KIND + 1))).scalars())
    if len(rows) > MAX_SOURCE_ROWS_PER_KIND:
        raise HTTPException(status_code=413, detail="Receivable source exceeds safe read limit")
    return rows


async def _verify_transaction(db: AsyncSession, *, read_only: bool) -> None:
    connection = await db.connection()
    if connection.dialect.name != "postgresql":
        raise RuntimeError("Receivable source requires PostgreSQL repeatable-read transaction")
    isolation = (await db.execute(text("SHOW transaction_isolation"))).scalar_one()
    mode = (await db.execute(text("SHOW transaction_read_only"))).scalar_one()
    if isolation.lower() != "repeatable read" or (read_only and mode.lower() != "on"):
        raise RuntimeError("Receivable source requires repeatable-read transaction and requested read-only mode")


async def load_receivable_source(db: AsyncSession, *, tenant_id: UUID, invoice_id: UUID,
                                 read_only: bool = True) -> ReceivableSourceBundle:
    """Read every V1 relation without a soft-delete filter and hash that snapshot.

    Production callers cannot bypass transaction verification. Disposable
    SQLite tests replace the verifier with an explicit no-op fixture.
    """
    await _verify_transaction(db, read_only=read_only)
    invoice = (await db.execute(select(Invoice).where(
        Invoice.tenant_id == tenant_id, Invoice.id == invoice_id,
    ))).scalar_one_or_none()
    if invoice is None:
        raise HTTPException(status_code=404, detail="Receivable source unavailable")
    order = (await db.execute(select(RepairOrder).where(
        RepairOrder.tenant_id == tenant_id, RepairOrder.id == invoice.repair_order_id,
    ))).scalar_one_or_none()
    if order is None:
        raise HTTPException(status_code=409, detail="Receivable source identity unresolved")
    customer_id = invoice.billed_customer_id or order.customer_id
    customer = (await db.execute(select(Customer).where(
        Customer.tenant_id == tenant_id, Customer.id == customer_id,
    ))).scalar_one_or_none()
    if customer is None or (invoice.billed_customer_id is None and order.customer_id != customer.id):
        raise HTTPException(status_code=409, detail="Receivable source identity unresolved")

    rows: dict[str, list[object]] = {
        "settlements": await _bounded(db, select(InvoiceSettlement).where(
            InvoiceSettlement.tenant_id == tenant_id, InvoiceSettlement.invoice_id == invoice_id)),
        "payments": await _bounded(db, select(Payment).where(
            Payment.tenant_id == tenant_id, Payment.invoice_id == invoice_id)),
        "payment_attempts": await _bounded(db, select(InvoicePaymentAttempt).where(
            InvoicePaymentAttempt.tenant_id == tenant_id, InvoicePaymentAttempt.invoice_id == invoice_id)),
        "ledger_events": await _bounded(db, select(InvoicePaymentLedgerEvent).where(
            InvoicePaymentLedgerEvent.tenant_id == tenant_id, InvoicePaymentLedgerEvent.invoice_id == invoice_id)),
        "refunds": await _bounded(db, select(PaymentRefund).where(
            PaymentRefund.tenant_id == tenant_id, PaymentRefund.invoice_id == invoice_id)),
        "overpayments": await _bounded(db, select(PaymentOverpayment).where(
            PaymentOverpayment.tenant_id == tenant_id, PaymentOverpayment.invoice_id == invoice_id)),
        # Customer-wide credit rows can change available credit. A credit that
        # targets this invoice under another customer is also evidence of an
        # identity conflict; never omit it from the fingerprint/review.
        "customer_credits": await _bounded(db, select(CustomerCreditEntry).where(
            CustomerCreditEntry.tenant_id == tenant_id,
            or_(CustomerCreditEntry.customer_id == customer.id,
                CustomerCreditEntry.target_invoice_id == invoice_id,
                CustomerCreditEntry.origin_overpayment_id.in_(select(PaymentOverpayment.id).where(
                    PaymentOverpayment.tenant_id == tenant_id,
                    PaymentOverpayment.invoice_id == invoice_id))))),
        "superseding_invoices": await _bounded(db, select(Invoice).where(
            Invoice.tenant_id == tenant_id, Invoice.supersedes_invoice_id == invoice_id)),
    }
    attempt_ids = [row.id for row in rows["payment_attempts"]]
    rows["provider_disputes"] = ([] if not attempt_ids else await _bounded(
        db, select(PaymentProviderDispute).where(
            PaymentProviderDispute.tenant_id == tenant_id,
            PaymentProviderDispute.attempt_id.in_(attempt_ids)),
    ))
    fingerprint = fingerprint_source_bundle(tenant_id=tenant_id, invoice=invoice,
                                            order=order, customer=customer, linked_rows=rows)
    return ReceivableSourceBundle(invoice=invoice, order=order, customer=customer,
                                  linked_rows=rows, fingerprint=fingerprint)
