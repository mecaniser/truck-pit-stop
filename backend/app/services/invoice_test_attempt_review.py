"""Read-only recognition of one privileged, audited test-reservation release.

A failure code supplied by the ordinary staff API is insufficient. This proof
consumes trusted append-only operational evidence and the complete no-money
history, and never writes, retries payment, or contacts a provider.
"""
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation

from sqlalchemy import or_, select

from app.core.dependencies import user_has_permission
from app.db.models.customer import Customer
from app.db.models.invoice_settlement import (
    CustomerCreditEntry,
    InvoicePaymentAttempt,
    InvoicePaymentLedgerEvent,
    InvoiceSettlement,
    PaymentAccountingLink,
    PaymentOverpayment,
    PaymentProviderDispute,
    PaymentRefund,
    ProviderSettlementEntry,
)
from app.db.models.payment import Payment
from app.db.models.repair_order import RepairOrder
from app.db.models.tenant import Tenant
from app.db.models.user import User

TEST_RELEASE_CODE = "owner_attested_test_attempt"


def _amount(value):
    # Missing, boolean and nonfinite evidence is unknown, never zero.
    if value is None or isinstance(value, bool):
        raise ValueError("Missing money evidence")
    result = Decimal(str(value))
    if not result.is_finite():
        raise ValueError("Invalid money evidence")
    return result


def _utc(value):
    if not isinstance(value, datetime):
        raise TypeError("Missing event time")
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


async def reviewed_test_ancestor(db, invoice, parent, *, lock=False):
    """Qualify only the v1 same-order, single failed customer-portal QBO test."""
    if (parent.tenant_id != invoice.tenant_id or parent.repair_order_id != invoice.repair_order_id
            or parent.deleted_at is not None or parent.status.value != "cancelled"
            or not parent.voided_at or parent.zelle_pending_submitted_at is not None
            or parent.quickbooks_invoice_id or parent.quickbooks_synced_at
            or parent.quickbooks_sync_status == "synced"):
        return False

    async def read(model, condition):
        query = select(model).where(condition).execution_options(populate_existing=True)
        if lock:
            query = query.with_for_update(nowait=True)
        return list((await db.scalars(query)).all())

    # Referenced IDs are globally unique. Inspect every row referencing them,
    # including malformed foreign-tenant links, and fail closed on any mismatch.
    orders = await read(RepairOrder, RepairOrder.id == parent.repair_order_id)
    tenants = await read(Tenant, Tenant.id == parent.tenant_id)
    if len(orders) != 1 or len(tenants) != 1:
        return False
    order, tenant = orders[0], tenants[0]
    customers = await read(Customer, Customer.id == order.customer_id)
    if (order.tenant_id != parent.tenant_id or order.deleted_at is not None
            or not tenant.is_active or tenant.deleted_at is not None or len(customers) != 1
            or customers[0].tenant_id != parent.tenant_id or customers[0].deleted_at is not None
            or parent.billed_customer_id not in (None, order.customer_id)
            or invoice.billed_customer_id not in (None, order.customer_id)):
        return False
    settlements = await read(InvoiceSettlement, InvoiceSettlement.invoice_id == parent.id)
    if len(settlements) != 1:
        return False
    settlement = settlements[0]
    attempts = await read(InvoicePaymentAttempt, or_(InvoicePaymentAttempt.invoice_id == parent.id,
        InvoicePaymentAttempt.settlement_id == settlement.id))
    if len(attempts) != 1:
        return False
    attempt = attempts[0]
    if (settlement.tenant_id != parent.tenant_id or settlement.customer_id != order.customer_id
            or settlement.deleted_at is not None or settlement.state != "unpaid" or settlement.currency != "USD"
            or attempt.tenant_id != parent.tenant_id or attempt.invoice_id != parent.id
            or attempt.settlement_id != settlement.id or attempt.customer_id != order.customer_id
            or attempt.deleted_at is not None or attempt.state != "failed" or not attempt.failed_at
            or attempt.failure_code != TEST_RELEASE_CODE or attempt.source != "customer_portal"
            or attempt.provider != "quickbooks_payments" or attempt.rail != "card" or attempt.currency != "USD"
            or attempt.received_amount is not None or attempt.manual_evidence != {}
            or any(getattr(attempt, name) is not None for name in (
                "payment_id", "provider_intent_id", "provider_charge_id", "provider_event_id", "provider_reference"))
            or any(getattr(attempt, name) != 0 for name in (
                "applied_principal_amount", "unapplied_amount", "applied_card_fee_amount",
                "applied_card_fee_tax_amount", "processor_fee_amount"))
            or any(getattr(settlement, name) != 0 for name in (
                "confirmed_principal", "active_pending_principal", "unapplied_credit", "refund_pending"))):
        return False
    forbidden = (
        (Payment, or_(Payment.invoice_id == parent.id, Payment.invoice_payment_attempt_id == attempt.id)),
        (PaymentAccountingLink, or_(PaymentAccountingLink.invoice_id == parent.id, PaymentAccountingLink.attempt_id == attempt.id)),
        (PaymentRefund, or_(PaymentRefund.invoice_id == parent.id, PaymentRefund.source_attempt_id == attempt.id)),
        (PaymentOverpayment, or_(PaymentOverpayment.invoice_id == parent.id, PaymentOverpayment.source_attempt_id == attempt.id)),
        (PaymentProviderDispute, PaymentProviderDispute.attempt_id == attempt.id),
        (ProviderSettlementEntry, ProviderSettlementEntry.attempt_id == attempt.id),
        (CustomerCreditEntry, or_(CustomerCreditEntry.target_invoice_id == parent.id,
            CustomerCreditEntry.origin_overpayment_id.in_(select(PaymentOverpayment.id).where(
                or_(PaymentOverpayment.invoice_id == parent.id, PaymentOverpayment.source_attempt_id == attempt.id))))),
    )
    for model, condition in forbidden:
        if await read(model, condition):
            return False
    ledgers = await read(InvoicePaymentLedgerEvent, or_(InvoicePaymentLedgerEvent.invoice_id == parent.id,
        InvoicePaymentLedgerEvent.settlement_id == settlement.id, InvoicePaymentLedgerEvent.attempt_id == attempt.id))
    ledgers.sort(key=lambda row: (row.sequence, str(row.id)))
    if (len(ledgers) < 2 or settlement.last_event_sequence != len(ledgers)
            or [row.sequence for row in ledgers] != list(range(1, len(ledgers) + 1))
            or ledgers[0].event_type != "attempt_created" or ledgers[-1].event_type != "payment_failed"):
        return False
    terminal = ledgers[-1]
    evidence = terminal.evidence_snapshot
    if (not isinstance(evidence, dict) or evidence.get("failure_code") != TEST_RELEASE_CODE
            or evidence.get("schema") != "owner-attested-test-reservation-release-v1"
            or evidence.get("classification") != TEST_RELEASE_CODE
            or evidence.get("operation") != "release_exact_internal_test_reservation"
            or evidence.get("provider_contacted") is not False or evidence.get("provider_verified") is not False
            or any(not isinstance(evidence.get(key), str) or not evidence[key].strip()
                for key in ("attestation", "evidence_source"))
            or not terminal.idempotency_key or not terminal.actor_user_id
            or terminal.actor_role_snapshot not in {"garage_owner", "garage_admin"}
            or terminal.new_state != "unpaid"):
        return False
    allowed_marker_keys = {"failure_code", "schema", "classification", "operation",
        "provider_contacted", "provider_verified", "attestation", "evidence_source", "executed_by"}
    if (set(evidence) - allowed_marker_keys
            or "executed_by" in evidence and (not isinstance(evidence["executed_by"], str) or not evidence["executed_by"].strip())):
        return False
    actors = await read(User, User.id == terminal.actor_user_id)
    if (len(actors) != 1 or actors[0].tenant_id != parent.tenant_id or actors[0].deleted_at is not None
            or not actors[0].is_active or actors[0].role.value not in {"garage_owner", "garage_admin"}
            or not user_has_permission(actors[0], "payments")):
        return False
    try:
        created_at, failed_at = _utc(attempt.created_at), _utc(attempt.failed_at)
        released_at = _utc(terminal.occurred_at)
        # PostgreSQL NOW() is transaction-start while failed_at uses wall time.
        # Permit a bounded transaction offset, never unrelated release dates.
        if (failed_at < created_at or released_at < created_at
                or abs(released_at - failed_at) > timedelta(minutes=5)
                or max(created_at, failed_at, released_at) > datetime.now(UTC) + timedelta(minutes=5)):
            return False
        principal = _amount(attempt.principal_amount)
        if principal <= 0:
            return False
        pending = Decimal(0)
        for index, row in enumerate(ledgers):
            if (row.tenant_id != parent.tenant_id or row.invoice_id != parent.id
                    or row.settlement_id != settlement.id or row.attempt_id != attempt.id
                    or row.customer_id != order.customer_id
                    or any(_amount(getattr(row, name)) != 0 for name in (
                        "principal_delta", "unapplied_delta", "refund_pending_delta"))):
                return False
            delta = _amount(row.pending_delta)
            if index == 0:
                details = row.evidence_snapshot
                if (delta != principal or row.prior_state != "unpaid" or row.new_state != "payment_pending"
                        or not isinstance(details, dict) or set(details) != {"source", "rail", "provider"}
                        or details != {"source": "customer_portal", "rail": "card", "provider": "quickbooks_payments"}):
                    return False
            elif index == len(ledgers) - 1:
                if delta != -principal or row.prior_state != "payment_pending" or row.new_state != "unpaid":
                    return False
            else:
                details = row.evidence_snapshot
                if (row.event_type != "provider_reconciliation_failed" or delta != 0
                        or not isinstance(details, dict)
                        or row.prior_state != "payment_pending" or row.new_state != "payment_pending"
                        or set(details) != {"failure_code", "provider", "provider_account", "provider_intent_id"}
                        or details.get("provider_account") != attempt.provider_account_id
                        or details.get("provider_account") is not None and not isinstance(details["provider_account"], str)
                        or details.get("failure_code") != "quickbooks_payment_outcome_unknown"
                        or details.get("provider") != "quickbooks_payments"
                        or details.get("provider_intent_id") is not None):
                    return False
            pending += delta
            snapshot = row.money_snapshot
            if (pending < 0 or not isinstance(snapshot, dict)
                    or _amount(snapshot.get("principal_total")) != _amount(settlement.principal_total)
                    or _amount(snapshot.get("active_pending_principal")) != pending
                    or any(_amount(snapshot.get(name)) != 0 for name in (
                        "confirmed_principal", "unapplied_credit", "refund_pending"))):
                return False
        return pending == 0
    except (InvalidOperation, ValueError, TypeError):
        return False
