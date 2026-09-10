"""Exact-manifest administrative quarantine. Never calls a provider or releases holds."""
from datetime import datetime, timezone
from decimal import Decimal
from hashlib import sha256
import json
from uuid import UUID

from sqlalchemy import select, or_

from app.db.models.invoice import Invoice
from app.db.models.invoice_settlement import (InvoiceSettlement, InvoicePaymentAttempt, PaymentRefund, PaymentAccountingLink,
    InvoicePaymentLedgerEvent, PaymentOverpayment, CustomerCreditEntry, ProviderSettlementEntry)
from app.db.models.payment import Payment
from app.db.models.provider_outbox import ProviderOutboxEvent
from app.services.invoice_accounting_policy import HISTORICAL_HOLD, locked_policy


def digest(value):
    return sha256(json.dumps(value, sort_keys=True, default=str, separators=(",", ":")).encode()).hexdigest()


def rows_digest(rows):
    def canonical(value):
        if isinstance(value, Decimal):
            return str(value.normalize())
        if isinstance(value, datetime):
            return value.replace(tzinfo=timezone.utc).isoformat() if value.tzinfo is None else value.astimezone(timezone.utc).isoformat()
        return value
    return digest([{column.name: canonical(getattr(row, column.name)) for column in row.__table__.columns}
                   for row in sorted(rows, key=lambda item: str(item.id))])


def financial_event(event):
    return event.event_type != "email.notification.v1"


async def inspect_invoice(db, *, tenant_id, invoice_id, cutoff, lock=False):
    invoice = await db.scalar(select(Invoice).where(Invoice.tenant_id == tenant_id, Invoice.id == invoice_id))
    if invoice is None:
        raise ValueError("Invoice missing or outside the exact tenant scope")
    if lock:
        await locked_policy(db, invoice, nowait=True)
        await db.refresh(invoice, attribute_names=[c.name for c in invoice.__table__.columns])
    groups = {"invoice": [invoice]}
    for model in (InvoiceSettlement, InvoicePaymentAttempt, PaymentRefund, PaymentAccountingLink, Payment,
                  InvoicePaymentLedgerEvent, PaymentOverpayment):
        query = select(model).where(model.tenant_id == tenant_id, model.invoice_id == invoice_id)
        groups[model.__tablename__] = list((await db.scalars(query.order_by(model.id))).all())
    groups["customer_credit_entries"] = list((await db.scalars(select(CustomerCreditEntry).where(
        CustomerCreditEntry.tenant_id == tenant_id, or_(CustomerCreditEntry.target_invoice_id == invoice_id,
        CustomerCreditEntry.origin_overpayment_id.in_([r.id for r in groups["payment_overpayments"]]))
    ).order_by(CustomerCreditEntry.id))).all())
    groups["provider_settlement_entries"] = list((await db.scalars(select(ProviderSettlementEntry).where(
        ProviderSettlementEntry.tenant_id == tenant_id,
        ProviderSettlementEntry.attempt_id.in_([r.id for r in groups["invoice_payment_attempts"]])
    ).order_by(ProviderSettlementEntry.id))).all())
    identifiers = {str(invoice_id)}
    for rows in groups.values():
        identifiers.update(str(row.id) for row in rows)
    # All financial envelope kinds are included, including credits whose source
    # or destination invoice is represented in payload instead of aggregate_id.
    events = list((await db.scalars(select(ProviderOutboxEvent).where(
        ProviderOutboxEvent.tenant_id == tenant_id,
        ProviderOutboxEvent.event_type != "email.notification.v1",
    ).order_by(ProviderOutboxEvent.id))).all())
    events = [e for e in events if str(e.aggregate_id) in identifiers or
              any(str(value) in identifiers for value in (e.payload or {}).values())]
    if lock and events:
        events = list((await db.scalars(select(ProviderOutboxEvent).where(
            ProviderOutboxEvent.tenant_id == tenant_id,
            ProviderOutboxEvent.id.in_([e.id for e in events]),
        ).order_by(ProviderOutboxEvent.id).with_for_update(nowait=True)
            .execution_options(populate_existing=True))).all())
    groups["financial_outbox"] = events
    blocked = []
    created = invoice.created_at.replace(tzinfo=timezone.utc) if invoice.created_at.tzinfo is None else invoice.created_at
    if invoice.deleted_at or created > cutoff:
        blocked.append("outside_historical_cutoff")
    if invoice.accounting_policy != "standard":
        blocked.append("nonstandard_policy")
    if invoice.quickbooks_invoice_id or invoice.quickbooks_synced_at or invoice.quickbooks_sync_status == "synced":
        blocked.append("existing_quickbooks_record")
    if any(e.status == "processing" or e.lock_token or e.locked_until for e in events):
        blocked.append("financial_lease_or_processing")
    if any(e.provider_message_id or e.status == "succeeded" for e in events):
        blocked.append("successful_financial_delivery")
    if any(a.state == "pending" for a in groups["invoice_payment_attempts"]):
        blocked.append("pending_payment_attempt")
    if any(r.state in {"pending", "manual_action_required"} for r in groups["payment_refunds"]):
        blocked.append("unresolved_refund")
    if any(str(getattr(p.status, "value", p.status)) in {"pending", "processing"} for p in groups["payments"]):
        blocked.append("pending_legacy_payment")
    if any(link.provider_object_id or link.sync_state == "synced" or link.synced_at
           or link.provider_deposit_id or link.provider_fee_journal_id for link in groups["payment_accounting_links"]):
        blocked.append("existing_accounting_link")
    if groups["customer_credit_entries"] or groups["payment_overpayments"] or groups["provider_settlement_entries"]:
        blocked.append("credit_or_payout_provenance_requires_individual_review")
    if any(s.active_pending_principal or s.refund_pending for s in groups["invoice_settlements"]):
        blocked.append("pending_settlement_money")
    result = {"invoice_id": str(invoice.id), "invoice_number": invoice.invoice_number,
        "prior_policy": invoice.accounting_policy,
        "quickbooks_invoice_id": invoice.quickbooks_invoice_id,
        "quickbooks_sync_status": invoice.quickbooks_sync_status,
        "blocked": sorted(set(blocked)),
        "fingerprints": {name: rows_digest(rows) for name, rows in groups.items()},
        "events": [{"id": str(e.id), "type": e.event_type, "status": e.status,
                    "attempts": e.attempt_count} for e in events]}
    return result, invoice, events


async def make_manifest(db, *, tenant_id, invoice_ids, cutoff, reason):
    if not reason.strip() or not invoice_ids or len(set(invoice_ids)) != len(invoice_ids):
        raise ValueError("An exact nonempty unique invoice list and review reason are required")
    if cutoff.tzinfo is None:
        raise ValueError("Cutoff must include a timezone")
    rows = []
    for invoice_id in sorted(invoice_ids, key=str):
        result, _, _ = await inspect_invoice(db, tenant_id=tenant_id, invoice_id=invoice_id, cutoff=cutoff)
        rows.append(result)
    return {"schema": "db048-historical-hold-v1", "tenant_id": str(tenant_id),
            "cutoff": cutoff.isoformat(), "reason": reason.strip(), "invoices": rows}


async def apply_manifest(db, manifest, *, expected_sha256):
    if digest(manifest) != expected_sha256 or manifest.get("schema") != "db048-historical-hold-v1":
        raise ValueError("Manifest digest/schema mismatch")
    rows = manifest["invoices"]
    ids = [row["invoice_id"] for row in rows]
    if not ids or len(ids) != len(set(ids)) or any(row["blocked"] for row in rows):
        raise ValueError("Apply requires a nonempty manifest containing eligible invoices only")
    tenant_id = UUID(manifest["tenant_id"])
    cutoff = datetime.fromisoformat(manifest["cutoff"])
    if cutoff.tzinfo is None or not manifest["reason"].strip():
        raise ValueError("Invalid manifest cutoff/reason")
    locked = []
    # Validate every invoice under the worker/payment shared lock order before
    # writing anything. Caller must commit once, or roll back the entire batch.
    for expected in sorted(rows, key=lambda row: row["invoice_id"]):
        current, invoice, events = await inspect_invoice(db, tenant_id=tenant_id,
            invoice_id=UUID(expected["invoice_id"]), cutoff=cutoff, lock=True)
        if current != expected or current["blocked"]:
            raise ValueError(f"Invoice changed since review: {expected['invoice_id']}")
        locked.append((invoice, events))
    now = datetime.now(timezone.utc)
    for invoice, events in locked:
        invoice.accounting_policy = HISTORICAL_HOLD
        for event in events:
            if event.status in {"pending", "deferred"}:
                event.status = "suppressed"
                event.payload = {**(event.payload or {}), "suppression_reason": HISTORICAL_HOLD,
                                 "historical_hold_manifest_sha256": expected_sha256}
                event.completed_at = now
    await db.flush()
    return {"manifest_sha256": expected_sha256, "tenant_id": str(tenant_id),
            "held_invoice_ids": ids, "held_count": len(ids), "provider_calls": 0,
            "automatic_release": False}
