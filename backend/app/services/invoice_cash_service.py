"""Exact full-cash receipts. Never sends a financial write to a provider."""
from datetime import datetime, timezone
from hashlib import sha256
import json
from uuid import UUID
from sqlalchemy import select
from app.core.config import settings
from app.core.dependencies import user_has_permission
from app.db.models.invoice import Invoice, InvoiceStatus
from app.db.models.invoice_settlement import (
    CustomerCreditEntry, InvoicePaymentAttempt, InvoicePaymentLedgerEvent,
    InvoiceSettlement, PaymentAccountingLink, PaymentOverpayment, PaymentRefund,
    ProviderSettlementEntry,
)
from app.db.models.payment import Payment, PaymentMethod, PaymentStatus
from app.db.models.provider_outbox import ProviderOutboxEvent
from app.db.models.quickbooks_connection import QuickBooksConnection
from app.db.models.repair_order import RepairOrderStatus
from app.db.models.user import UserRole
from app.services.invoice_accounting_policy import HISTORICAL_HOLD, locked_policy, LOCAL_CASH, LOCAL_CASH_SYNC
from app.services.invoice_settlement_service import (
    SettlementDomainError, _canonical_hash, _actor_snapshot, money,
    get_or_create_settlement, append_ledger_event, allocate_next_payment_number,
)


CASH_REVIEW_KEY = "cash_nonproduction_review"
OWNER_CASH_REVIEW_KEY = "cash_owner_attestation_review"
REVIEW_KEYS = {CASH_REVIEW_KEY, OWNER_CASH_REVIEW_KEY}


def owner_cash_review_target(event, invoice):
    """The owner exception is only for a held, ambiguous replacement export."""
    return bool(
        invoice.accounting_policy == HISTORICAL_HOLD
        and invoice.supersedes_invoice_id is not None
        and event.event_type == "quickbooks.invoice.sync.v1"
        and (event.payload or {}).get("cash_export_ambiguous") is True
    )


def event_history_digest(event):
    """Bind review to every original column except ordinary update metadata."""
    values = {}
    for column in event.__table__.columns:
        if column.name == "updated_at":
            continue
        value = getattr(event, column.name)
        # Migration 143 added a nullable audit to Invoice. A NULL audit must
        # retain pre-143 ancestor proofs; an actual audit remains history-bound.
        if isinstance(event, Invoice) and column.name == "tax_exemption" and value is None:
            continue
        if column.name == "payload":
            value = None if value is None else {key: item for key, item in value.items() if key not in REVIEW_KEYS}
        if isinstance(value, datetime):
            value = (value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)).isoformat()
        values[column.name] = value
    if isinstance(event, Invoice) and event.charge_adjustments:
        values["charge_adjustments"] = [event_history_digest(row) for row in sorted(event.charge_adjustments, key=lambda row: row.version)]
    return sha256(json.dumps(values, sort_keys=True, default=str, separators=(",", ":")).encode()).hexdigest()


def valid_sandbox_cash_review(event, invoice):
    review = (event.payload or {}).get(CASH_REVIEW_KEY)
    if not isinstance(review, dict):
        return False
    try:
        reviewed_at = datetime.fromisoformat(review["reviewed_at"])
        chain = review.get("supersedes_chain", [])
        ancestors = review.get("ancestor_reviews", [])
        if (not isinstance(chain, list) or not isinstance(ancestors, list)
                or any(not isinstance(item, str) for item in chain)
                or len(set(chain)) != len(chain)
                or any(not isinstance(item, dict) or item.get("invoice_id") not in chain for item in ancestors)):
            return False
        for item in chain:
            UUID(item)
        return bool(
            review["schema"] == "db048-sandbox-cash-review-v1"
            and review["tenant_id"] == str(invoice.tenant_id) == str(event.tenant_id)
            and review["invoice_id"] == str(invoice.id) == str(event.aggregate_id)
            and review["event_id"] == str(event.id)
            and review["event_type"] == event.event_type == "quickbooks.invoice.sync.v1"
            and review["event_status"] == event.status == "dead"
            and review["attempt_count"] == event.attempt_count and event.attempt_count > 0
            and review["original_history_sha256"] == event_history_digest(event)
            and review["observed_environment"] == "sandbox"
            and review["confirmation_environment"] == "production"
            and isinstance(review["confirmation_realm_id"], str) and review["confirmation_realm_id"].strip()
            and len(review["evidence_manifest_sha256"]) == 64
            and all(c in "0123456789abcdef" for c in review["evidence_manifest_sha256"])
            and reviewed_at.tzinfo is not None and reviewed_at <= datetime.now(timezone.utc)
            and isinstance(review["reviewer"], str) and review["reviewer"].strip()
            and not event.lock_token and not event.locked_until and not event.provider_message_id
        )
    except (KeyError, TypeError, ValueError):
        return False


def valid_owner_cash_review(event, invoice):
    review = (event.payload or {}).get(OWNER_CASH_REVIEW_KEY)
    if not isinstance(review, dict):
        return False
    try:
        reviewed_at = datetime.fromisoformat(review["reviewed_at"])
        chain = review.get("supersedes_chain", [])
        ancestors = review.get("ancestor_reviews", [])
        if (not isinstance(chain, list) or not isinstance(ancestors, list)
                or any(not isinstance(item, str) for item in chain)
                or len(set(chain)) != len(chain)
                or len(ancestors) != len(chain)
                or any(not isinstance(item, dict) or item.get("invoice_id") not in chain for item in ancestors)
                or {item.get("invoice_id") for item in ancestors} != set(chain)):
            return False
        for item in chain:
            UUID(item)
        return bool(
            review["schema"] == "db048-owner-cash-review-v1"
            and review["tenant_id"] == str(invoice.tenant_id) == str(event.tenant_id)
            and review["invoice_id"] == str(invoice.id) == str(event.aggregate_id)
            and review["invoice_history_sha256"] == event_history_digest(invoice)
            and review["event_id"] == str(event.id)
            and review["event_type"] == event.event_type == "quickbooks.invoice.sync.v1"
            and review["event_status"] == event.status
            and event.status in {"dead", "suppressed", "deferred"}
            and owner_cash_review_target(event, invoice)
            and review["attempt_count"] == event.attempt_count and event.attempt_count > 0
            and review["original_history_sha256"] == event_history_digest(event)
            and review["attestation"] == "no_provider_payment_cash_received"
            and review["provider_verified"] is False
            and isinstance(review["attestation_source"], str) and review["attestation_source"].strip()
            and len(review["evidence_manifest_sha256"]) == 64
            and all(c in "0123456789abcdef" for c in review["evidence_manifest_sha256"])
            and reviewed_at.tzinfo is not None and reviewed_at <= datetime.now(timezone.utc)
            and isinstance(review["reviewer"], str) and review["reviewer"].strip()
            and not event.lock_token and not event.locked_until and not event.provider_message_id
        )
    except (KeyError, TypeError, ValueError):
        return False


def cash_staff(actor):
    return bool(actor and actor.role in {UserRole.GARAGE_OWNER, UserRole.GARAGE_ADMIN, UserRole.RECEPTIONIST}
                and user_has_permission(actor, "payments"))


async def ancestor_financial_events(db, parent, *, lock=False):
    from app.services.provider_outbox_service import EMAIL_NOTIFICATION_EVENT
    query = select(ProviderOutboxEvent).where(ProviderOutboxEvent.tenant_id == parent.tenant_id,
        ProviderOutboxEvent.aggregate_id == parent.id, ProviderOutboxEvent.event_type != EMAIL_NOTIFICATION_EVENT)
    if lock:
        query = query.with_for_update(nowait=True)
    return list((await db.scalars(query.execution_options(populate_existing=True))).all())


async def local_void_ancestor_snapshot(db, parent, *, lock=False):
    events = await ancestor_financial_events(db, parent, lock=lock)
    if (getattr(parent.status, "value", parent.status) != "cancelled" or not parent.voided_at
            or parent.quickbooks_invoice_id or parent.quickbooks_sync_status != "voided"
            or not parent.quickbooks_synced_at or not events
            or any(e.event_type != "quickbooks.invoice.sync.v1" or e.status != "succeeded"
                or e.provider_message_id or e.lock_token or e.locked_until for e in events)):
        return None
    return {"invoice_id": str(parent.id), "invoice_sha256": event_history_digest(parent),
        "events": [{"event_id": str(e.id), "history_sha256": event_history_digest(e)}
                   for e in sorted(events, key=lambda item: str(item.id))]}


async def owner_attested_ancestor_snapshot(db, parent, *, lock=False):
    """Return an exact no-money snapshot, or None when owner review cannot qualify."""
    def query(model):
        statement = select(model).where(model.tenant_id == parent.tenant_id,
            model.invoice_id == parent.id).order_by(model.id).execution_options(populate_existing=True)
        return statement.with_for_update(nowait=True) if lock else statement

    attempts = list((await db.scalars(query(InvoicePaymentAttempt))).all())
    settlements = list((await db.scalars(query(InvoiceSettlement))).all())
    payments = list((await db.scalars(query(Payment))).all())
    links = list((await db.scalars(query(PaymentAccountingLink))).all())
    ledgers = list((await db.scalars(query(InvoicePaymentLedgerEvent))).all())
    refunds = list((await db.scalars(query(PaymentRefund))).all())
    overpayments = list((await db.scalars(query(PaymentOverpayment))).all())
    credits_query = select(CustomerCreditEntry).where(CustomerCreditEntry.tenant_id == parent.tenant_id,
        CustomerCreditEntry.target_invoice_id == parent.id).order_by(CustomerCreditEntry.id).execution_options(populate_existing=True)
    if lock:
        credits_query = credits_query.with_for_update(nowait=True)
    credits = list((await db.scalars(credits_query)).all())
    provider_query = select(ProviderSettlementEntry).where(
        ProviderSettlementEntry.tenant_id == parent.tenant_id,
        ProviderSettlementEntry.attempt_id.in_([attempt.id for attempt in attempts])).execution_options(populate_existing=True)
    if lock:
        provider_query = provider_query.with_for_update(nowait=True)
    provider_rows = [] if not attempts else list((await db.scalars(provider_query)).all())
    events = await ancestor_financial_events(db, parent, lock=lock)

    if (getattr(parent.status, "value", parent.status) != "cancelled"
            or parent.quickbooks_invoice_id or parent.quickbooks_synced_at
            or parent.quickbooks_sync_status == "synced"
            or parent.zelle_pending_submitted_at is not None
            or payments or links or refunds or overpayments or credits or provider_rows
            or len(settlements) > 1
            or any(event.event_type != "quickbooks.invoice.sync.v1"
                or event.status not in {"dead", "suppressed", "deferred"}
                or event.provider_message_id or event.lock_token or event.locked_until for event in events)):
        return None
    if any(attempt.state not in {"failed", "expired"}
            or attempt.failure_code != "owner_attested_no_card_payment"
            or attempt.payment_id or attempt.provider_intent_id or attempt.provider_charge_id
            or attempt.provider_event_id or attempt.provider_reference
            or attempt.received_amount is not None
            or any(money(getattr(attempt, field)) != 0 for field in (
                "applied_principal_amount", "unapplied_amount", "applied_card_fee_amount",
                "applied_card_fee_tax_amount", "processor_fee_amount")) for attempt in attempts):
        return None
    attempt_ids = {attempt.id for attempt in attempts}
    if any(ledger.attempt_id not in attempt_ids
            or ledger.event_type not in {"attempt_created", "payment_failed", "payment_expired"}
            or money(ledger.principal_delta) != 0
            or money(ledger.unapplied_delta) != 0
            or money(ledger.refund_pending_delta) != 0 for ledger in ledgers):
        return None
    if any(any(money(getattr(settlement, field)) != 0 for field in (
            "confirmed_principal", "active_pending_principal", "unapplied_credit", "refund_pending"))
            for settlement in settlements):
        return None

    groups = {
        "settlements": settlements, "attempts": attempts, "ledgers": ledgers,
        "outbox": sorted(events, key=lambda item: str(item.id)),
    }
    return {
        "invoice_id": str(parent.id),
        "invoice_sha256": event_history_digest(parent),
        **{name: [{"id": str(row.id), "history_sha256": event_history_digest(row)} for row in rows]
           for name, rows in groups.items()},
    }


async def reviewed_cash_ancestry_reason(db, invoice, *, lock=False, reviews=None):
    seen = {invoice.id}
    parent_id = invoice.supersedes_invoice_id
    chain = []
    while parent_id:
        if parent_id in seen:
            return "Invoice replacement history requires review before local cash."
        seen.add(parent_id)
        chain.append(str(parent_id))
        parent = await db.scalar(select(Invoice).where(Invoice.id == parent_id,
            Invoice.tenant_id == invoice.tenant_id).execution_options(populate_existing=True))
        if parent is None:
            return "Invoice replacement history requires review before local cash."
        if lock:
            await locked_policy(db, parent, nowait=True)
            await db.refresh(parent, attribute_names=[column.name for column in Invoice.__table__.columns])
        owner_reviews = [review for review in (reviews or [])
            if review.get("schema") == "db048-owner-cash-review-v1"]
        if owner_reviews:
            snapshot = await owner_attested_ancestor_snapshot(db, parent, lock=lock)
            proofs = [next((proof for proof in review.get("ancestor_reviews", [])
                if proof.get("invoice_id") == str(parent.id)), None) for review in owner_reviews]
            if (not snapshot or any(not proof
                    or proof.get("schema") != "db048-owner-attested-ancestor-review-v1"
                    or proof.get("snapshot") != snapshot for proof in proofs)):
                return "A replaced invoice has payment or export history outside the owner's reviewed cash attestation."
        elif parent.quickbooks_invoice_id or parent.quickbooks_synced_at:
            snapshot = await local_void_ancestor_snapshot(db, parent, lock=lock)
            proofs = [proof for review in (reviews or []) for proof in review.get("ancestor_reviews", [])
                if isinstance(proof, dict) and proof.get("invoice_id") == str(parent.id)]
            if not snapshot or len(proofs) != len(reviews or []) or not proofs or any(
                    proof.get("schema") != "db048-local-void-ancestor-review-v1"
                    or proof.get("snapshot") != snapshot
                    or proof.get("confirmation_realm_id") != review.get("confirmation_realm_id")
                    or proof.get("evidence_manifest_sha256") != review.get("evidence_manifest_sha256")
                    for review, proof in zip(reviews, proofs)):
                return "A replaced invoice has QuickBooks accounting history. Review it before local cash."
        if not owner_reviews:
            for model in (InvoicePaymentAttempt, Payment, PaymentAccountingLink, InvoicePaymentLedgerEvent):
                if await db.scalar(select(model.id).where(model.tenant_id == invoice.tenant_id,
                        model.invoice_id == parent.id).limit(1)):
                    return "A replaced invoice has payment activity. Resolve it before local cash."
        settlement = await db.scalar(select(InvoiceSettlement).where(InvoiceSettlement.tenant_id == invoice.tenant_id,
            InvoiceSettlement.invoice_id == parent.id).execution_options(populate_existing=True))
        if not owner_reviews and settlement and (settlement.last_event_sequence or any(money(getattr(settlement, name)) != 0
                for name in ("confirmed_principal", "active_pending_principal", "unapplied_credit", "refund_pending"))):
            return "A replaced invoice has payment activity. Resolve it before local cash."
        parent_id = parent.supersedes_invoice_id
    if reviews and any(review.get("supersedes_chain", []) != chain for review in reviews):
        return "Invoice replacement history changed after review. Accounting review is required before cash."
    return None


async def cash_eligibility(db, invoice, settlement, *, lock=False):
    if invoice.cash_export_review_required:
        return "Previous QuickBooks accounting activity requires review before local cash.", []
    if (invoice.deleted_at or invoice.voided_at or invoice.is_internal
            or invoice.status not in {InvoiceStatus.SENT, InvoiceStatus.OVERDUE}):
        return "Only an active unpaid customer invoice can be paid in cash.", []
    if invoice.quickbooks_invoice_id or invoice.quickbooks_synced_at:
        return "This invoice already has a QuickBooks accounting record.", []
    if invoice.zelle_pending_submitted_at is not None:
        return "A previously submitted Zelle payment must be resolved before cash.", []
    if settlement.legacy_reconciliation_status not in {"native", "reconciled"}:
        return "This older invoice needs payment-history review before cash.", []
    if (money(settlement.principal_total) <= 0 or any(money(getattr(settlement, name)) != 0
            for name in ("confirmed_principal", "active_pending_principal", "unapplied_credit", "refund_pending"))
            or settlement.last_event_sequence):
        return "Cash requires the full invoice with no existing payment activity.", []
    for model in (InvoicePaymentAttempt, Payment, PaymentAccountingLink, InvoicePaymentLedgerEvent):
        if await db.scalar(select(model.id).where(model.tenant_id == invoice.tenant_id,
                model.invoice_id == invoice.id).limit(1)):
            return "Cash cannot be mixed with existing or historical payments.", []
    query = select(ProviderOutboxEvent).where(ProviderOutboxEvent.tenant_id == invoice.tenant_id,
        ProviderOutboxEvent.aggregate_id == invoice.id)
    if lock:
        query = query.with_for_update()
    all_events = list((await db.scalars(query)).all())
    from app.services.provider_outbox_service import EMAIL_NOTIFICATION_EVENT
    # Only known nonfinancial delivery events are ignored, never suppressed.
    # SMS delivery is currently immediate and has no invoice provider-outbox type.
    events = [event for event in all_events if event.event_type != EMAIL_NOTIFICATION_EVENT]
    if not events and invoice.quickbooks_sync_status not in {None, "pending", "not_synced", "not_required", "awaiting_payment"}:
        return "Previous accounting activity must be reviewed before local cash.", events
    for event in events:
        if CASH_REVIEW_KEY in (event.payload or {}) and not valid_sandbox_cash_review(event, invoice):
            return "The reviewed export history changed. Accounting review is required before cash.", events
        if OWNER_CASH_REVIEW_KEY in (event.payload or {}) and not valid_owner_cash_review(event, invoice):
            return "The owner-attested export history changed. Accounting review is required before cash.", events
        if event.event_type != "quickbooks.invoice.sync.v1":
            return "Existing invoice delivery activity requires review before local cash.", events
        if event.status == "processing" or event.lock_token:
            return "Invoice export is in progress or its outcome is unresolved. Try again after reconciliation.", events
        if event.status == "succeeded" or event.provider_message_id:
            return "This invoice already has QuickBooks export history.", events
        if event.status not in {"pending", "dead", "suppressed", "deferred"}:
            return "The invoice export outcome requires review.", events
        if not (valid_sandbox_cash_review(event, invoice) or valid_owner_cash_review(event, invoice)) and ((event.payload or {}).get("cash_export_ambiguous")
                or event.attempt_count and not (event.payload or {}).get("cash_no_dispatch")
                and (event.payload or {}).get("cash_export_ambiguous", True)):
            return "Previous export attempts have an unverified outcome. Accounting review is required before cash.", events
    if any(valid_sandbox_cash_review(event, invoice) or valid_owner_cash_review(event, invoice) for event in events):
        reviews = [event.payload[CASH_REVIEW_KEY] for event in events if valid_sandbox_cash_review(event, invoice)]
        reviews.extend(event.payload[OWNER_CASH_REVIEW_KEY] for event in events if valid_owner_cash_review(event, invoice))
        reason = await reviewed_cash_ancestry_reason(db, invoice, lock=lock, reviews=reviews)
        if reason:
            return reason, events
    return None, events


async def reconcile_export_absence(db, invoice, events):
    # Owner attestation is an explicit business risk acceptance, not provider
    # verification. Never call QuickBooks and mislabel it as an absence check.
    attempted = [event for event in events if not valid_owner_cash_review(event, invoice)
        and (valid_sandbox_cash_review(event, invoice)
            or event.attempt_count and not (event.payload or {}).get("cash_no_dispatch"))]
    if not attempted:
        return
    from app.services.quickbooks_accounting_service import _request, _escape_query
    from app.services.quickbooks_sync_service import _refresh_if_needed
    connection = await db.scalar(select(QuickBooksConnection).where(
        QuickBooksConnection.tenant_id == invoice.tenant_id,
        QuickBooksConnection.status == "connected").with_for_update())
    def matches_context(event):
        if valid_sandbox_cash_review(event, invoice):
            review = event.payload[CASH_REVIEW_KEY]
            return (settings.QUICKBOOKS_ACCOUNTING_ENVIRONMENT == "production"
                and review["confirmation_realm_id"] == connection.realm_id)
        return (event.payload.get("cash_export_realm") == connection.realm_id
            and event.payload.get("cash_export_environment") == settings.QUICKBOOKS_ACCOUNTING_ENVIRONMENT)
    if not connection or not connection.realm_id or any(not matches_context(event) for event in attempted):
        raise SettlementDomainError("cash_export_unverified", "The original QuickBooks company must be verified before cash.")
    try:
        await _refresh_if_needed(connection)
        # Legacy writers truncate DocNumber to 21 characters; search BOTH shapes.
        # Any collision blocks conversion, even if customer/source markers differ.
        numbers = {invoice.invoice_number, invoice.invoice_number[:21]}
        for event in attempted:
            if valid_sandbox_cash_review(event, invoice):
                for ancestor_id in event.payload[CASH_REVIEW_KEY].get("supersedes_chain", []):
                    parent = await db.scalar(select(Invoice).where(Invoice.id == UUID(ancestor_id),
                        Invoice.tenant_id == invoice.tenant_id))
                    if parent is None:
                        raise SettlementDomainError("cash_export_unverified", "Invoice replacement history changed.")
                    numbers.update({parent.invoice_number, parent.invoice_number[:21]})
        for number in numbers:
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
        "cash_export_review_required", "supersedes_invoice_id"])
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
