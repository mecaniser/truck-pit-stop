"""Exact full-cash receipts. Never sends a financial write to a provider."""
from datetime import datetime, timezone
from sqlalchemy import select
from app.core.config import settings
from app.core.dependencies import user_has_permission
from app.db.models.invoice import Invoice, InvoiceStatus
from app.db.models.invoice_settlement import InvoicePaymentAttempt, PaymentAccountingLink
from app.db.models.payment import Payment, PaymentMethod, PaymentStatus
from app.db.models.provider_outbox import ProviderOutboxEvent
from app.db.models.quickbooks_connection import QuickBooksConnection
from app.db.models.repair_order import RepairOrderStatus
from app.db.models.user import UserRole
from app.services.invoice_accounting_policy import locked_policy, LOCAL_CASH, LOCAL_CASH_SYNC
from app.services.invoice_settlement_service import (
    SettlementDomainError, _canonical_hash, _actor_snapshot, money,
    get_or_create_settlement, append_ledger_event, allocate_next_payment_number,
)


def cash_staff(actor):
    return bool(actor and actor.role in {UserRole.GARAGE_OWNER, UserRole.GARAGE_ADMIN, UserRole.RECEPTIONIST}
                and user_has_permission(actor, "payments"))


async def cash_eligibility(db, invoice, settlement, *, lock=False):
    if invoice.cash_export_review_required:
        return "Previous QuickBooks company changes require accounting review before local cash.", []
    if (invoice.deleted_at or invoice.voided_at or invoice.is_internal
            or invoice.status not in {InvoiceStatus.SENT, InvoiceStatus.OVERDUE}):
        return "Only an active unpaid customer invoice can be paid in cash.", []
    if invoice.quickbooks_invoice_id or invoice.quickbooks_synced_at:
        return "This invoice already has a QuickBooks accounting record.", []
    if invoice.zelle_pending_submitted_at is not None:
        return "A previously submitted Zelle payment must be resolved before cash.", []
    if (money(settlement.principal_total) <= 0 or any(money(getattr(settlement, name)) != 0
            for name in ("confirmed_principal", "active_pending_principal", "unapplied_credit", "refund_pending"))
            or settlement.last_event_sequence or settlement.legacy_reconciliation_status != "native"):
        return "Cash requires the full invoice with no existing payment activity.", []
    for model in (InvoicePaymentAttempt, Payment, PaymentAccountingLink):
        if await db.scalar(select(model.id).where(model.tenant_id == invoice.tenant_id,
                model.invoice_id == invoice.id).limit(1)):
            return "Cash cannot be mixed with existing or historical payments.", []
    query = select(ProviderOutboxEvent).where(ProviderOutboxEvent.tenant_id == invoice.tenant_id,
        ProviderOutboxEvent.aggregate_id == invoice.id)
    if lock:
        query = query.with_for_update()
    events = list((await db.scalars(query)).all())
    if not events and invoice.quickbooks_sync_status not in {None, "pending", "not_synced", "not_required"}:
        return "Previous accounting activity must be reviewed before local cash.", events
    for event in events:
        if event.event_type != "quickbooks.invoice.sync.v1":
            return "Existing invoice delivery activity requires review before local cash.", events
        if event.status == "processing" or event.lock_token:
            return "Invoice export is in progress or its outcome is unresolved. Try again after reconciliation.", events
        if event.status == "succeeded" or event.provider_message_id:
            return "This invoice already has QuickBooks export history.", events
        if event.status not in {"pending", "dead", "suppressed"}:
            return "The invoice export outcome requires review.", events
        if ((event.payload or {}).get("cash_export_ambiguous")
                or event.attempt_count and not (event.payload or {}).get("cash_no_dispatch")
                and (event.payload or {}).get("cash_export_ambiguous", True)):
            return "Previous export attempts have an unverified outcome. Accounting review is required before cash.", events
    return None, events


async def reconcile_export_absence(db, invoice, events):
    attempted = [event for event in events if event.attempt_count and not (event.payload or {}).get("cash_no_dispatch")]
    if not attempted:
        return
    from app.services.quickbooks_accounting_service import _request, _escape_query
    from app.services.quickbooks_sync_service import _refresh_if_needed
    connection = await db.scalar(select(QuickBooksConnection).where(
        QuickBooksConnection.tenant_id == invoice.tenant_id,
        QuickBooksConnection.status == "connected").with_for_update())
    if not connection or not connection.realm_id or any(
        event.payload.get("cash_export_realm") != connection.realm_id
        or event.payload.get("cash_export_environment") != settings.QUICKBOOKS_ACCOUNTING_ENVIRONMENT
        for event in attempted
    ):
        raise SettlementDomainError("cash_export_unverified", "The original QuickBooks company must be verified before cash.")
    try:
        await _refresh_if_needed(connection)
        # Legacy writers truncate DocNumber to 21 characters; search BOTH shapes.
        # Any collision blocks conversion, even if customer/source markers differ.
        for number in {invoice.invoice_number, invoice.invoice_number[:21]}:
            payload = await _request(connection, "GET", "query", params={"query":
                f"select * from Invoice where DocNumber = '{_escape_query(number)}' maxresults 2"})
            query = payload.get("QueryResponse")
            if not isinstance(query, dict) or ("Invoice" in query and not isinstance(query["Invoice"], list)):
                raise ValueError("Unknown provider query shape")
            if query.get("Invoice") or query.get("totalCount", 0):
                raise SettlementDomainError("cash_export_exists", "QuickBooks contains a matching invoice. Local-only cash is not available.")
    except SettlementDomainError:
        raise
    except Exception as exc:
        raise SettlementDomainError("cash_export_unverified", "QuickBooks export could not be verified. No cash payment was recorded.", retryable=True) from exc


async def confirm_full_cash(db, *, invoice, tenant, customer_id, actor,
                            expected_settlement_version, idempotency_key, note=None):
    if not cash_staff(actor) or actor.tenant_id != tenant.id:
        raise SettlementDomainError("invoice_not_found", "Invoice not found.", status_code=404)
    if (invoice.tenant_id != tenant.id or not tenant.is_active or tenant.deleted_at
            or invoice.repair_order.tenant_id != tenant.id
            or invoice.repair_order.customer_id != customer_id
            or invoice.repair_order.deleted_at
            or invoice.repair_order.status == RepairOrderStatus.CANCELLED
            or invoice.repair_order.customer.tenant_id != tenant.id
            or invoice.repair_order.customer.deleted_at):
        raise SettlementDomainError("invoice_not_found", "Invoice not found.", status_code=404)
    if not settings.INVOICE_SPLIT_PAYMENTS_ENABLED or not tenant.invoice_split_payments_enabled:
        raise SettlementDomainError("split_payments_disabled", "Invoice settlement is not enabled for this shop.")
    request_hash = _canonical_hash({"operation": "full_cash", "invoice_id": str(invoice.id),
        "actor_id": str(actor.id), "version": expected_settlement_version, "note": note or ""})
    settlement = await get_or_create_settlement(db, invoice=invoice, tenant=tenant, customer_id=customer_id)
    if (settlement.tenant_id != tenant.id or settlement.invoice_id != invoice.id
            or settlement.customer_id != customer_id):
        raise SettlementDomainError("invoice_not_found", "Invoice not found.", status_code=404)
    await locked_policy(db, invoice, nowait=True)
    # Refresh after acquiring serialization, not from the earlier endpoint read.
    await db.refresh(invoice, attribute_names=["accounting_policy", "status", "deleted_at", "voided_at",
        "quickbooks_invoice_id", "quickbooks_synced_at", "quickbooks_sync_status", "is_internal", "zelle_pending_submitted_at",
        "cash_export_review_required"])
    existing = await db.scalar(select(InvoicePaymentAttempt).where(
        InvoicePaymentAttempt.tenant_id == tenant.id, InvoicePaymentAttempt.idempotency_key == idempotency_key))
    if existing:
        if existing.request_hash != request_hash or existing.rail != "cash":
            raise SettlementDomainError("idempotency_conflict", "This key was used for another payment request.")
        return existing.payment_id, settlement
    if settlement.version != expected_settlement_version:
        raise SettlementDomainError("stale_settlement_version", "The invoice changed. Refresh before recording cash.", current_version=settlement.version)
    reason, events = await cash_eligibility(db, invoice, settlement, lock=True)
    if reason:
        raise SettlementDomainError("cash_unavailable", reason)
    await reconcile_export_absence(db, invoice, events)
    now = datetime.now(timezone.utc)
    for event in events:
        event.status = "suppressed"
        event.payload = {**(event.payload or {}), "suppression_reason": LOCAL_CASH_SYNC,
                         "suppressed_by_user_id": str(actor.id)}
        event.completed_at = now
        event.lock_token = None
        event.locked_until = None
    invoice.accounting_policy = LOCAL_CASH
    invoice.quickbooks_sync_status = LOCAL_CASH_SYNC
    amount = money(settlement.principal_total)
    actor_id, actor_name, actor_role = _actor_snapshot(actor)
    attempt = InvoicePaymentAttempt(tenant_id=tenant.id, invoice_id=invoice.id,
        settlement_id=settlement.id, customer_id=customer_id, source="staff_cash", rail="cash",
        provider="manual", state="confirmed", principal_amount=amount, provider_charge_amount=amount,
        received_amount=amount, applied_principal_amount=amount, provider_configuration_version=0,
        actor_user_id=actor_id, actor_name_snapshot=actor_name, actor_role_snapshot=actor_role,
        subject_type="staff", subject_id=actor_id, idempotency_key=idempotency_key,
        request_hash=request_hash, confirmed_at=now, manual_evidence={"note": note or "", "accounting_policy": LOCAL_CASH})
    db.add(attempt)
    await db.flush()
    payment = Payment(tenant_id=tenant.id, invoice_id=invoice.id,
        payment_number=await allocate_next_payment_number(db, tenant.id), amount=amount,
        method=PaymentMethod.CASH, status=PaymentStatus.COMPLETED, payment_provider="manual",
        recorded_by_user_id=actor_id, notes=note, invoice_payment_attempt_id=attempt.id)
    db.add(payment)
    await db.flush()
    attempt.payment_id = payment.id
    settlement.confirmed_principal = amount
    settlement.version += 1
    prior = settlement.state
    settlement.state = "paid"
    settlement.accounting_sync_status = LOCAL_CASH_SYNC
    invoice.status = InvoiceStatus.PAID
    invoice.paid_at = now
    invoice.repair_order.status = RepairOrderStatus.PAID
    await append_ledger_event(db, settlement=settlement, attempt=attempt, actor=actor,
        event_type="cash_payment_confirmed", idempotency_key=f"cash-confirm:{idempotency_key}",
        prior_state=prior, new_state="paid", principal_delta=amount,
        evidence={"payment_id": str(payment.id), "accounting_policy": LOCAL_CASH,
                  "export_event_ids": [str(event.id) for event in events]})
    await db.flush()
    return payment.id, settlement
