"""Conservative DB-135 source triage; never an approval or collectible decision."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.db.models.invoice import InvoiceStatus
from app.db.models.payment import PaymentStatus
from app.db.models.repair_order import RepairOrderStatus
from app.services.invoice_settlement_service import invoice_money_snapshot, money
from app.services.receivable_attestation_source import ReceivableSourceBundle


ZERO = Decimal("0.00")


@dataclass(frozen=True)
class ReceivableTriage:
    # Only a source-review candidate. A human must supply current operator or
    # receipt-level evidence before any immutable attestation can be approved.
    review_path: str | None
    principal: Decimal
    completed_payment_total: Decimal
    hold_reasons: tuple[str, ...]
    source_fingerprint: str


def triage_receivable_source(bundle: ReceivableSourceBundle) -> ReceivableTriage:
    invoice, order, customer = bundle.invoice, bundle.order, bundle.customer
    rows = bundle.linked_rows
    principal = money(invoice_money_snapshot(invoice)[0])
    completed = money(sum((money(row.amount) for row in rows["payments"]
                           if row.status == PaymentStatus.COMPLETED), ZERO))
    reasons: list[str] = []
    imported = invoice.source == "easy_truck_shop_import" or invoice.accounting_policy == "historical_export_hold"
    if imported:
        reasons.append("ets_owned_history")
    if invoice.deleted_at or invoice.voided_at or invoice.status not in {
        InvoiceStatus.SENT, InvoiceStatus.OVERDUE, InvoiceStatus.PAID,
    } or invoice.is_internal:
        reasons.append("invoice_not_collectible_candidate")
    if order.deleted_at or order.status == RepairOrderStatus.CANCELLED or customer.deleted_at:
        reasons.append("source_identity_inactive")
    if rows["superseding_invoices"]:
        reasons.append("invoice_superseded")
    if rows["settlements"]:
        reasons.append("settlement_exists")
    if principal <= ZERO:
        reasons.append("principal_not_positive")
    if any(getattr(row, "deleted_at", None) is not None for kind, children in rows.items()
           if kind != "superseding_invoices" for row in children):
        reasons.append("financial_source_tombstoned")
    if any(row.source == "easy_truck_shop_import" for row in rows["payments"]):
        reasons.append("mixed_ets_payment")
    if rows["payment_attempts"] or rows["ledger_events"] or rows["refunds"] or rows["overpayments"] or rows["provider_disputes"]:
        reasons.append("other_financial_evidence")
    overpayment_ids = {row.id for row in rows["overpayments"]}
    if any(row.target_invoice_id == invoice.id or row.origin_overpayment_id in overpayment_ids
           for row in rows["customer_credits"]):
        reasons.append("invoice_credit_evidence")
    if any(row.target_invoice_id == invoice.id and row.customer_id != customer.id
           for row in rows["customer_credits"]):
        reasons.append("credit_customer_conflict")

    review_path = None
    if invoice.status in {InvoiceStatus.SENT, InvoiceStatus.OVERDUE}:
        if rows["payments"]:
            reasons.append("open_invoice_has_payment_evidence")
        if not reasons:
            review_path = "open_operator_review"
    elif invoice.status == InvoiceStatus.PAID:
        if any(row.status != PaymentStatus.COMPLETED for row in rows["payments"]):
            reasons.append("paid_invoice_has_unresolved_payment")
        if completed < principal:
            reasons.append("paid_tender_shortfall")
        elif completed > principal:
            reasons.append("paid_tender_overage")
        if not reasons:
            review_path = "paid_receipt_review"
    return ReceivableTriage(review_path=review_path, principal=principal,
                            completed_payment_total=completed, hold_reasons=tuple(reasons),
                            source_fingerprint=bundle.fingerprint)
