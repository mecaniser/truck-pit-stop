"""DB-135 read-only, source-separated customer account projection."""
from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import HTTPException
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models.customer import Customer
from app.db.models.invoice import Invoice, InvoiceStatus
from app.db.models.invoice_settlement import (
    CustomerCreditEntry, InvoicePaymentLedgerEvent, InvoiceSettlement, PaymentOverpayment,
)
from app.db.models.payment import Payment, PaymentStatus
from app.db.models.repair_order import RepairOrder
from app.db.models.tenant import Tenant
from app.services.invoice_settlement_service import invoice_money_snapshot, money


ZERO = Decimal("0.00")
BUCKETS = ("current", "days_1_30", "days_31_60", "days_61_90", "days_90_plus")
BAD_BASELINE_EVENTS = {"legacy_paid_snapshot", "legacy_invalid_payment_baseline"}
TRUSTED_SETTLEMENT_STATES = {"native", "reconciled"}
MAX_ACCOUNT_INVOICES = 5000
MAX_ACCOUNT_PAYMENTS = 10000
MAX_ACCOUNT_CREDITS = 10000


def _money(value: Decimal | None) -> str:
    return str(money(value))


def bucket_for(due_date: date | None, as_of: date) -> str:
    if due_date is None:
        return "undated_due"
    days = max(0, (as_of - due_date).days)
    if days == 0:
        return "current"
    if days <= 30:
        return "days_1_30"
    if days <= 60:
        return "days_31_60"
    if days <= 90:
        return "days_61_90"
    return "days_90_plus"


def _cursor_key(tenant_id: UUID, customer_id: UUID, source_filter: str) -> bytes:
    return f"{tenant_id}:{customer_id}:{source_filter}".encode()


def row_sort_key(row: dict) -> tuple[str, str, str]:
    return (row["occurred_at"] or row["source_date"] or "", row["kind"], row["id"])


def encode_cursor(tenant_id: UUID, customer_id: UUID, source_filter: str, row: dict) -> str:
    payload = {"v": 2, "scope": hashlib.sha256(_cursor_key(tenant_id, customer_id, source_filter)).hexdigest(),
               "after": list(row_sort_key(row))}
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    signature = hmac.new(settings.SECRET_KEY.encode(), raw, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(raw + signature).decode().rstrip("=")


def decode_cursor(token: str | None, tenant_id: UUID, customer_id: UUID, source_filter: str) -> tuple[str, str, str] | None:
    if token is None:
        return None
    try:
        decoded = base64.urlsafe_b64decode(token + "=" * (-len(token) % 4))
        if base64.urlsafe_b64encode(decoded).decode().rstrip("=") != token:
            raise ValueError("noncanonical")
        raw, signature = decoded[:-32], decoded[-32:]
        if not hmac.compare_digest(signature, hmac.new(settings.SECRET_KEY.encode(), raw, hashlib.sha256).digest()):
            raise ValueError("signature")
        payload = json.loads(raw)
        after = payload.get("after")
        if payload.get("v") != 2 or payload.get("scope") != hashlib.sha256(_cursor_key(tenant_id, customer_id, source_filter)).hexdigest():
            raise ValueError("scope")
        if not isinstance(after, list) or len(after) != 3 or any(not isinstance(part, str) or len(part) > 100 for part in after):
            raise ValueError("position")
        return tuple(after)
    except (ValueError, TypeError, KeyError, UnicodeDecodeError, binascii.Error, json.JSONDecodeError):
        raise HTTPException(status_code=422, detail="Invalid account cursor")


def trusted_settlement(invoice: Invoice, settlement: InvoiceSettlement | None, *,
                       customer_id: UUID, bad_baseline: bool) -> bool:
    if settlement is None or settlement.deleted_at is not None or bad_baseline:
        return False
    if settlement.legacy_reconciliation_status not in TRUSTED_SETTLEMENT_STATES:
        return False
    if settlement.currency != "USD":
        return False
    if settlement.tenant_id != invoice.tenant_id or settlement.invoice_id != invoice.id or settlement.customer_id != customer_id:
        return False
    principal = money(invoice_money_snapshot(invoice)[0])
    confirmed = money(settlement.confirmed_principal)
    return money(settlement.principal_total) == principal and ZERO <= confirmed <= principal


def eligible_credit_issue(entry: CustomerCreditEntry, overpayments: dict[UUID, PaymentOverpayment]) -> bool:
    if entry.entry_type != "issued" or not entry.origin_overpayment_id:
        return False
    origin = overpayments.get(entry.origin_overpayment_id)
    return bool(origin and origin.state == "credited" and origin.consented_at and entry.consent_channel
                and origin.customer_id == entry.customer_id and origin.tenant_id == entry.tenant_id)


def _credit_remaining(entries: list[CustomerCreditEntry], overpayments: dict[UUID, PaymentOverpayment]) -> Decimal:
    direct_used: dict[UUID, Decimal] = {}
    for entry in entries:
        if entry.source_entry_id and entry.entry_type in {"applied", "refunded", "reversed"}:
            direct_used[entry.source_entry_id] = money(direct_used.get(entry.source_entry_id, ZERO) + money(entry.amount))
    total = ZERO
    for entry in entries:
        if not eligible_credit_issue(entry, overpayments):
            continue
        total = money(total + max(ZERO, money(entry.amount) - direct_used.get(entry.id, ZERO)))
    return total


def credit_effect(entry: CustomerCreditEntry, entries_by_id: dict[UUID, CustomerCreditEntry],
                  overpayments: dict[UUID, PaymentOverpayment]) -> str:
    if eligible_credit_issue(entry, overpayments):
        return "increase"
    parent = entries_by_id.get(entry.source_entry_id)
    if parent and eligible_credit_issue(parent, overpayments) and entry.entry_type in {"applied", "refunded", "reversed"}:
        return "decrease"
    return "audit"


def _row(kind: str, source: str, id_: UUID, occurred: datetime | None, date_basis: str,
         invoice_id: UUID | None, amount: Decimal | None, remaining: Decimal | None,
         route: str | None, reason: str | None = None, source_date: date | None = None,
         invoice_number: str | None = None) -> dict:
    return {
        "id": str(id_), "kind": kind, "source_owner": source,
        "occurred_at": occurred.isoformat() if occurred else None,
        "source_date": source_date.isoformat() if source_date else None,
        "date_basis": date_basis, "invoice_id": str(invoice_id) if invoice_id else None,
        "invoice_number": invoice_number,
        "amount": _money(amount) if amount is not None else None,
        "remaining_principal": _money(remaining) if remaining is not None else None,
        "drilldown_route": route, "review_reason": reason,
    }


async def account_snapshot(db: AsyncSession, *, tenant_id: UUID, customer_id: UUID) -> dict:
    customer = (await db.execute(select(Customer).where(
        Customer.id == customer_id, Customer.tenant_id == tenant_id, Customer.deleted_at.is_(None),
    ))).scalar_one_or_none()
    tenant = (await db.execute(select(Tenant).where(Tenant.id == tenant_id, Tenant.is_active.is_(True)))).scalar_one_or_none()
    if not customer or not tenant:
        raise HTTPException(status_code=404, detail="Customer not found")
    try:
        local_zone = ZoneInfo(tenant.timezone)
    except (ZoneInfoNotFoundError, TypeError):
        raise HTTPException(status_code=503, detail="Customer account timezone unavailable")
    now = datetime.now(timezone.utc)
    as_of = now.astimezone(local_zone).date()
    name = customer.company_name or " ".join(part for part in (customer.first_name, customer.last_name) if part) or "Customer"
    # A non-null bill-to snapshot is authoritative only while its customer
    # exists. The RO link discovers a masked exception, never a new owner.
    invoices = (await db.execute(
        select(Invoice, RepairOrder, Customer)
        .join(RepairOrder, and_(RepairOrder.id == Invoice.repair_order_id,
                                RepairOrder.tenant_id == Invoice.tenant_id))
        .outerjoin(Customer, and_(Customer.id == Invoice.billed_customer_id,
                                  Customer.tenant_id == Invoice.tenant_id,
                                  Customer.deleted_at.is_(None)))
        .where(Invoice.tenant_id == tenant_id, Invoice.deleted_at.is_(None),
               or_(Invoice.billed_customer_id == customer_id,
                   and_(Invoice.billed_customer_id.is_(None), RepairOrder.customer_id == customer_id),
                   and_(RepairOrder.customer_id == customer_id,
                        Invoice.billed_customer_id.is_not(None), Customer.id.is_(None))))
        .limit(MAX_ACCOUNT_INVOICES + 1)
    )).all()
    if len(invoices) > MAX_ACCOUNT_INVOICES:
        raise HTTPException(status_code=413, detail="Account activity exceeds safe read limit")
    invoice_ids = [invoice.id for invoice, _, _ in invoices]
    settlements: dict[UUID, InvoiceSettlement] = {}
    bad_baseline: set[UUID] = set()
    superseded_ids: set[UUID] = set()
    payments: list[Payment] = []
    if invoice_ids:
        superseded_ids = set((await db.execute(select(Invoice.supersedes_invoice_id).where(
            Invoice.tenant_id == tenant_id, Invoice.deleted_at.is_(None),
            Invoice.supersedes_invoice_id.in_(invoice_ids),
        ))).scalars())
        settlements = {row.invoice_id: row for row in (await db.execute(select(InvoiceSettlement).where(
            InvoiceSettlement.tenant_id == tenant_id, InvoiceSettlement.invoice_id.in_(invoice_ids),
        ))).scalars()}
        bad_baseline = set((await db.execute(select(InvoicePaymentLedgerEvent.invoice_id).where(
            InvoicePaymentLedgerEvent.tenant_id == tenant_id,
            InvoicePaymentLedgerEvent.invoice_id.in_(invoice_ids),
            InvoicePaymentLedgerEvent.event_type.in_(BAD_BASELINE_EVENTS),
        ))).scalars())
        payments = list((await db.execute(select(Payment).where(
            Payment.tenant_id == tenant_id, Payment.invoice_id.in_(invoice_ids), Payment.deleted_at.is_(None),
        ).limit(MAX_ACCOUNT_PAYMENTS + 1))).scalars())
        if len(payments) > MAX_ACCOUNT_PAYMENTS:
            raise HTTPException(status_code=413, detail="Account activity exceeds safe read limit")
    credits = list((await db.execute(select(CustomerCreditEntry).where(
        CustomerCreditEntry.tenant_id == tenant_id, CustomerCreditEntry.customer_id == customer_id,
    ).limit(MAX_ACCOUNT_CREDITS + 1))).scalars())
    if len(credits) > MAX_ACCOUNT_CREDITS:
        raise HTTPException(status_code=413, detail="Account activity exceeds safe read limit")
    origin_ids = {row.origin_overpayment_id for row in credits if row.origin_overpayment_id}
    credit_by_id = {row.id: row for row in credits}
    overpayments = {} if not origin_ids else {row.id: row for row in (await db.execute(select(PaymentOverpayment).where(
        PaymentOverpayment.tenant_id == tenant_id, PaymentOverpayment.id.in_(origin_ids),
        PaymentOverpayment.deleted_at.is_(None),
    ))).scalars()}

    buckets = {key: ZERO for key in (*BUCKETS, "undated_due")}
    collectible = ZERO
    review_native = review_ets = 0
    unverified_native_invoices = 0
    rows: list[dict] = []
    source_by_invoice: dict[UUID, str] = {}
    masked_invoice_ids: set[UUID] = set()
    order_by_invoice: dict[UUID, UUID] = {invoice.id: order.id for invoice, order, _ in invoices}
    number_by_invoice: dict[UUID, str] = {invoice.id: invoice.invoice_number for invoice, _, _ in invoices}
    mixed_payment_invoice_ids = {payment.invoice_id for payment in payments if payment.source == "easy_truck_shop_import"}
    for invoice, order, bill_to in invoices:
        if order.deleted_at is not None:
            imported = invoice.source == "easy_truck_shop_import" or invoice.accounting_policy == "historical_export_hold"
            eligible = (invoice.status in {InvoiceStatus.SENT, InvoiceStatus.PAID, InvoiceStatus.OVERDUE}
                        and not invoice.is_internal and not invoice.voided_at and invoice.id not in superseded_ids)
            if not eligible:
                continue
            if imported:
                review_ets += 1
            else:
                review_native += 1
                unverified_native_invoices += 1
            source_by_invoice[invoice.id] = "review_required"
            masked_invoice_ids.add(invoice.id)
            rows.append(_row("invoice", "review_required", invoice.id, None, "order_deleted",
                             invoice.id, None, None, None, "Repair order was deleted"))
            continue
        orphan = invoice.billed_customer_id is not None and bill_to is None
        if orphan:
            if invoice.source == "easy_truck_shop_import" or invoice.accounting_policy == "historical_export_hold":
                review_ets += 1
            else:
                review_native += 1
                if (invoice.status in {InvoiceStatus.SENT, InvoiceStatus.PAID, InvoiceStatus.OVERDUE}
                        and not invoice.is_internal and not invoice.voided_at and invoice.id not in superseded_ids):
                    unverified_native_invoices += 1
            source_by_invoice[invoice.id] = "review_required"
            masked_invoice_ids.add(invoice.id)
            rows.append(_row("invoice", "review_required", invoice.id, None, "identity_unresolved",
                             invoice.id, None, None, None, "Bill-to snapshot no longer resolves"))
            continue
        if invoice.billed_customer_id is not None and invoice.billed_customer_id != customer_id:
            continue
        if invoice.billed_customer_id is None and order.customer_id != customer_id:
            continue
        imported = invoice.source == "easy_truck_shop_import" or invoice.accounting_policy == "historical_export_hold"
        if imported:
            source = "ets_history"
            if invoice.accounting_policy == "historical_export_hold" and invoice.source != "easy_truck_shop_import":
                review_ets += 1
        elif invoice.status in {InvoiceStatus.SENT, InvoiceStatus.PAID, InvoiceStatus.OVERDUE} and not invoice.is_internal and not invoice.voided_at and invoice.id not in superseded_ids:
            source = "native" if invoice.id not in mixed_payment_invoice_ids and trusted_settlement(invoice, settlements.get(invoice.id),
                                                      customer_id=customer_id, bad_baseline=invoice.id in bad_baseline) else "review_required"
            if source == "review_required":
                review_native += 1
                unverified_native_invoices += 1
        else:
            # Drafts, voids, cancelled revisions and internal invoices are not AR.
            continue
        source_by_invoice[invoice.id] = source
        remaining = None
        if source == "native":
            settlement = settlements[invoice.id]
            remaining = max(ZERO, money(settlement.principal_total) - money(settlement.confirmed_principal))
            collectible = money(collectible + remaining)
            due = (invoice.due_date.replace(tzinfo=invoice.due_date.tzinfo or timezone.utc)
                   .astimezone(local_zone).date()) if invoice.due_date else None
            buckets[bucket_for(due, as_of)] = money(buckets[bucket_for(due, as_of)] + remaining)
        occurred = invoice.created_at if source != "ets_history" else None
        rows.append(_row("invoice", source, invoice.id, occurred,
                         "created_at" if occurred else ("ets_invoiced_at" if invoice.ets_invoiced_at else "source_date_unavailable"), invoice.id,
                         money(invoice.total_amount), remaining,
                         f"/dashboard/repair-orders?selected={order.id}",
                         source_date=invoice.ets_invoiced_at if source == "ets_history" else None,
                         invoice_number=invoice.invoice_number))
        rows[-1]["principal_total"] = _money(settlements[invoice.id].principal_total) if source == "native" else None
        rows[-1]["settled_principal"] = _money(settlements[invoice.id].confirmed_principal) if source == "native" else None
    for payment in payments:
        if payment.invoice_id in masked_invoice_ids:
            continue
        parent_source = source_by_invoice.get(payment.invoice_id)
        if parent_source is None:
            continue
        source = "ets_history" if payment.source == "easy_truck_shop_import" or parent_source == "ets_history" else parent_source
        if parent_source == "ets_history" and payment.source != "easy_truck_shop_import":
            source = "review_required"
            review_ets += 1
        if payment.source == "easy_truck_shop_import" and parent_source == "native":
            source = "review_required"
        if payment.status != PaymentStatus.COMPLETED and source == "native":
            source = "review_required"
            review_native += 1
        occurred = None if source == "ets_history" else payment.created_at
        rows.append(_row("payment", source, payment.id, occurred,
                         "created_at" if occurred else "source_date_unavailable", payment.invoice_id,
                         money(payment.amount), None, f"/dashboard/repair-orders?selected={order_by_invoice[payment.invoice_id]}",
                         None if payment.status == PaymentStatus.COMPLETED else f"payment_{payment.status.value}",
                         invoice_number=number_by_invoice.get(payment.invoice_id)))
        rows[-1]["payment_status"] = payment.status.value
    for credit in credits:
        kind = "refund" if credit.entry_type == "refunded" else "credit"
        credit_source = "native"
        if credit.entry_type == "issued" and not eligible_credit_issue(credit, overpayments):
            credit_source = "review_required"
            review_native += 1
        rows.append(_row(kind, credit_source, credit.id, credit.occurred_at, "occurred_at",
                         credit.target_invoice_id, money(credit.amount), None,
                         f"/dashboard/repair-orders?selected={order_by_invoice[credit.target_invoice_id]}" if credit.target_invoice_id in order_by_invoice else None,
                         credit.entry_type, invoice_number=number_by_invoice.get(credit.target_invoice_id)))
        rows[-1]["credit_action"] = credit.entry_type
        rows[-1]["credit_effect"] = credit_effect(credit, credit_by_id, overpayments)
    rows.sort(key=row_sort_key, reverse=True)
    return {
        "as_of_date": as_of.isoformat(), "generated_at": now.isoformat(), "currency": "USD",
        "customer": {"id": str(customer.id), "name": name},
        "native": {"collectible": _money(collectible), "collectible_complete": unverified_native_invoices == 0,
                   "unverified_invoice_count": unverified_native_invoices,
                   **{key: _money(value) for key, value in buckets.items()},
                   "unapplied_credit": _money(_credit_remaining(credits, overpayments)),
                   "review_required_count": review_native},
        "ets_history": {"observed_open_balance": None, "balance_basis": "unavailable",
                        "review_required_count": review_ets, "collectible": False},
        "transactions": rows,
    }
