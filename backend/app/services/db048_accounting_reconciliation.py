"""DB-048 accounting and provider reconciliation workers.

Every delivery is first resolved to a tenant-scoped persisted envelope.  No
provider call is allowed to run from identifiers carried only in an outbox
payload.  This is the one-writer boundary for QBO invoice payments/refunds and
the gross-to-net boundary for Stripe payouts.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Awaitable, Callable, Optional
from uuid import UUID, uuid4

import stripe
from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import settings
from app.db.models.customer import Customer
from app.db.models.invoice import Invoice
from app.db.models.invoice import InvoiceStatus
from app.db.models.invoice_settlement import (
    CustomerCreditEntry,
    InvoicePaymentAttempt,
    InvoicePaymentLedgerEvent,
    InvoiceSettlement,
    PaymentAccountingLink,
    PaymentOverpayment,
    PaymentProviderDispute,
    PaymentRefund,
    ProviderSettlementBatch,
    ProviderSettlementEntry,
    TenantPaymentProviderConfiguration,
)
from app.db.models.payment import Payment, PaymentStatus
from app.db.models.provider_outbox import ProviderOutboxEvent, ProviderOutboxStatus
from app.db.models.quickbooks_connection import QuickBooksConnection
from app.db.models.repair_order import RepairOrder, RepairOrderStatus
from app.db.models.tenant import Tenant
from app.db.session import AsyncSessionLocal
from app.services.invoice_settlement_service import (
    SettlementDomainError,
    ZERO,
    append_ledger_event,
    confirm_attempt,
    expire_due_attempts,
    fail_attempt,
    locked_accessible_invoice_for_attempt,
    money,
    settlement_state,
)
from app.services.quickbooks_accounting_service import (
    QuickBooksAccountingError,
    _ensure_service_item,
    _escape_query,
    _query,
    _request,
    ensure_customer,
    quickbooks_invoice_memo,
)
from app.services.quickbooks_payments_service import (
    QuickBooksPaymentError,
    get_charge as get_quickbooks_charge,
    get_refund as get_quickbooks_refund,
    is_successful_charge as is_successful_quickbooks_charge,
    refund_charge as refund_quickbooks_charge,
)
from app.services.quickbooks_service import (
    QuickBooksOAuthError,
    refresh_access_token,
    save_token_set,
)
from app.services.stripe_payment_finalization import (
    validate_db048_stripe_payment_intent,
)


PAYMENT_ACCOUNTING_EVENT = "invoice_payment.accounting_sync"
REFUND_ACCOUNTING_EVENT = "invoice_refund.accounting_sync"
REVERSAL_ACCOUNTING_EVENT = "payment_reversal.accounting_sync"
DISPUTE_ACCOUNTING_EVENT = "payment_dispute.accounting_sync"
DISPUTE_RECOVERY_ACCOUNTING_EVENT = "payment_dispute_recovery.accounting_sync"
CREDIT_ACCOUNTING_EVENT = "customer_credit.accounting_sync"
PROVIDER_REFUND_EVENT = "payment_refund.provider_submit"
PAYOUT_RECONCILIATION_EVENT = "stripe_payout.reconcile"
ACCOUNTING_EVENTS = {
    PAYMENT_ACCOUNTING_EVENT,
    REFUND_ACCOUNTING_EVENT,
    REVERSAL_ACCOUNTING_EVENT,
    DISPUTE_ACCOUNTING_EVENT,
    DISPUTE_RECOVERY_ACCOUNTING_EVENT,
    CREDIT_ACCOUNTING_EVENT,
}
WORKER_EVENTS = ACCOUNTING_EVENTS | {PROVIDER_REFUND_EVENT, PAYOUT_RECONCILIATION_EVENT}
CARD_RECONCILE_RETRY_MINUTES = 5


class DB048ReconciliationError(RuntimeError):
    def __init__(self, message: str, *, retryable: bool = False):
        super().__init__(message)
        self.retryable = retryable


async def _refresh_accounting_connection_if_needed(
    db: AsyncSession,
    connection: QuickBooksConnection,
) -> None:
    """Persist rotated QBO credentials before an accounting provider call.

    Intuit access tokens expire after roughly one hour.  DB-048 outbox work can
    legitimately run later than the mutation that enqueued it, so using the
    snapshotted connection without refreshing turns a healthy refresh token
    into a terminal HTTP 401.  Persisting the rotated token set before the QBO
    write also closes the crash window that would otherwise discard Intuit's
    newly rotated refresh token.
    """
    expires = connection.access_token_expires_at
    now = datetime.now(timezone.utc)
    if expires and expires > now + timedelta(minutes=5):
        return
    try:
        token_set = await refresh_access_token(connection)
        save_token_set(
            connection,
            realm_id=connection.realm_id or "",
            token_set=token_set,
            now=now,
        )
    except QuickBooksOAuthError as exc:
        connection.last_token_refresh_error = str(exc)[:500]
        raise DB048ReconciliationError(
            "QuickBooks credentials could not be refreshed",
            retryable=True,
        ) from exc
    connection.last_token_refresh_at = now
    connection.last_token_refresh_error = None
    await db.commit()


@dataclass(frozen=True)
class AccountingEnvelope:
    event_id: UUID
    tenant: Tenant
    link: PaymentAccountingLink
    attempt: InvoicePaymentAttempt
    payment: Payment
    invoice: Invoice
    customer: Customer
    connection: QuickBooksConnection
    config: TenantPaymentProviderConfiguration
    settlement: InvoiceSettlement
    refund: Optional[PaymentRefund] = None
    dispute: Optional[PaymentProviderDispute] = None


@dataclass(frozen=True)
class CreditAccountingEnvelope:
    event_id: UUID
    tenant: Tenant
    link: PaymentAccountingLink
    application: CustomerCreditEntry
    origin: CustomerCreditEntry
    overpayment: PaymentOverpayment
    source_attempt: InvoicePaymentAttempt
    source_payment: Payment
    source_accounting_link: PaymentAccountingLink
    target_invoice: Invoice
    target_customer: Customer
    target_settlement: InvoiceSettlement
    connection: QuickBooksConnection
    config: TenantPaymentProviderConfiguration


async def _record_card_reconciliation_failure(
    db: AsyncSession,
    *,
    attempt: InvoicePaymentAttempt,
    code: str,
    now: datetime,
) -> None:
    """Keep a mismatched provider result pending and append safe evidence."""
    attempt.failure_code = code[:100]
    attempt.version += 1
    attempt.expires_at = now + timedelta(minutes=CARD_RECONCILE_RETRY_MINUTES)
    settlement = await db.scalar(
        select(InvoiceSettlement)
        .where(
            InvoiceSettlement.id == attempt.settlement_id,
            InvoiceSettlement.tenant_id == attempt.tenant_id,
        )
        .with_for_update()
    )
    if settlement is None:
        raise DB048ReconciliationError("provider_settlement_identity_mismatch")
    provider_identity = attempt.provider_intent_id or attempt.provider_charge_id or "unknown"
    event_key = f"{attempt.provider}-reconciliation:{attempt.id}:{provider_identity}:{code}"
    existing = await db.scalar(
        select(InvoicePaymentLedgerEvent.id).where(
            InvoicePaymentLedgerEvent.tenant_id == attempt.tenant_id,
            InvoicePaymentLedgerEvent.idempotency_key == event_key,
        )
    )
    if existing is None:
        await append_ledger_event(
            db,
            settlement=settlement,
            attempt=attempt,
            event_type="provider_reconciliation_failed",
            idempotency_key=event_key,
            actor=None,
            prior_state=settlement.state,
            new_state=settlement.state,
            evidence={
                "failure_code": code[:100],
                "provider": attempt.provider,
                "provider_account": attempt.provider_account_id,
                "provider_intent_id": attempt.provider_intent_id,
            },
        )


async def reconcile_due_card_attempts(
    db: AsyncSession,
    *,
    tenant_id: Optional[UUID] = None,
    limit: int = 100,
    retrieve_intent: Callable[..., Any] = stripe.PaymentIntent.retrieve,
    cancel_intent: Callable[..., Any] = stripe.PaymentIntent.cancel,
) -> dict[str, int]:
    """Reconcile expired card holds against their snapshotted provider.

    A provider success is applied even when it arrives after the local hold
    deadline.  An explicitly cancelled/failed intent releases the reservation;
    non-terminal or unreachable intents retain it and are revisited shortly.
    """
    now = datetime.now(timezone.utc)
    query = select(InvoicePaymentAttempt.id).where(
        InvoicePaymentAttempt.state == "pending",
        InvoicePaymentAttempt.rail == "card",
        InvoicePaymentAttempt.provider.in_(["stripe_connect", "quickbooks_payments"]),
        InvoicePaymentAttempt.expires_at.is_not(None),
        InvoicePaymentAttempt.expires_at <= now,
    )
    if tenant_id:
        query = query.where(InvoicePaymentAttempt.tenant_id == tenant_id)
    attempt_ids = list((await db.execute(
        query.order_by(InvoicePaymentAttempt.expires_at).limit(limit)
    )).scalars().all())
    result = {"checked": 0, "confirmed": 0, "released": 0, "deferred": 0}
    terminal_release = {"canceled"}
    cancelable = {"requires_payment_method", "requires_confirmation", "requires_action"}
    for attempt_id in attempt_ids:
        attempt = (await db.execute(select(InvoicePaymentAttempt).where(
            InvoicePaymentAttempt.id == attempt_id,
        ).with_for_update())).scalar_one_or_none()
        if not attempt or attempt.state != "pending":
            result["deferred"] += 1
            continue
        try:
            await locked_accessible_invoice_for_attempt(db, attempt)
        except SettlementDomainError as exc:
            # Inaccessible invoice/order lifecycle is an intentional hard
            # boundary. Do not retrieve/cancel provider money or mutate the
            # attempt, reservation, settlement, invoice, or order.
            if exc.code == "invoice_not_found":
                result["deferred"] += 1
                continue
            raise
        result["checked"] += 1
        if attempt.provider == "quickbooks_payments":
            if not attempt.provider_charge_id:
                await _record_card_reconciliation_failure(
                    db,
                    attempt=attempt,
                    code="quickbooks_payment_outcome_unknown",
                    now=now,
                )
                result["deferred"] += 1
                continue
            connection = await db.scalar(select(QuickBooksConnection).where(
                QuickBooksConnection.tenant_id == attempt.tenant_id,
                QuickBooksConnection.status == "connected",
                QuickBooksConnection.deleted_at.is_(None),
            ))
            if not connection:
                await _record_card_reconciliation_failure(
                    db,
                    attempt=attempt,
                    code="quickbooks_connection_unavailable",
                    now=now,
                )
                result["deferred"] += 1
                continue
            try:
                charge = await get_quickbooks_charge(
                    connection=connection,
                    charge_id=attempt.provider_charge_id,
                )
            except QuickBooksPaymentError:
                await _record_card_reconciliation_failure(
                    db,
                    attempt=attempt,
                    code="quickbooks_payment_outcome_unknown",
                    now=now,
                )
                result["deferred"] += 1
                continue
            if money(charge.amount) != money(attempt.provider_charge_amount):
                # The synchronous capture path durably queues the compensating
                # refund as soon as it receives this response. Maintenance
                # keeps the reservation until that refund reaches finality.
                await _record_card_reconciliation_failure(
                    db,
                    attempt=attempt,
                    code="provider_payment_mismatch",
                    now=now,
                )
                result["deferred"] += 1
                continue
            if is_successful_quickbooks_charge(charge):
                tenant = await db.get(Tenant, attempt.tenant_id)
                if not tenant:
                    raise DB048ReconciliationError("Card attempt tenant was not found")
                await confirm_attempt(
                    db,
                    attempt_id=attempt.id,
                    tenant=tenant,
                    actor=None,
                    expected_attempt_version=attempt.version,
                    idempotency_key=f"qbp-reconcile:{attempt.id}:{charge.id}:succeeded",
                    received_principal=money(attempt.principal_amount),
                    provider_charge_id=charge.id,
                    provider_event_id=f"reconcile:{charge.id}:succeeded",
                    verified_provider_fact=True,
                )
                result["confirmed"] += 1
                continue
            if charge.status.casefold() in {"failed", "declined", "cancelled", "canceled", "voided"}:
                await fail_attempt(
                    db,
                    attempt_id=attempt.id,
                    tenant_id=attempt.tenant_id,
                    actor=None,
                    expected_attempt_version=attempt.version,
                    failure_code="provider_reservation_expired",
                    idempotency_key=f"qbp-reconcile:{attempt.id}:{charge.id}:expired",
                    expired=True,
                )
                result["released"] += 1
            else:
                attempt.expires_at = now + timedelta(minutes=CARD_RECONCILE_RETRY_MINUTES)
                result["deferred"] += 1
            continue
        if not attempt.provider_intent_id:
            attempt.expires_at = now + timedelta(minutes=CARD_RECONCILE_RETRY_MINUTES)
            result["deferred"] += 1
            continue
        try:
            intent = retrieve_intent(
                attempt.provider_intent_id,
                stripe_account=attempt.provider_account_id,
            )
            validated = await validate_db048_stripe_payment_intent(
                db=db,
                payment_intent=intent,
                trusted_provider_account_id=attempt.provider_account_id,
                attempt=attempt,
                allowed_statuses={
                    "succeeded", "canceled", "requires_payment_method",
                    "requires_confirmation", "requires_action", "processing",
                    "requires_capture",
                },
            )
            intent_id = validated.payment_intent_id
            status_value = validated.status
            if status_value == "succeeded":
                tenant = await db.get(Tenant, attempt.tenant_id)
                if not tenant:
                    raise DB048ReconciliationError("Card attempt tenant was not found")
                await confirm_attempt(
                    db,
                    attempt_id=attempt.id,
                    tenant=tenant,
                    actor=None,
                    expected_attempt_version=attempt.version,
                    idempotency_key=f"stripe-reconcile:{attempt.provider_account_id}:{intent_id}:succeeded",
                    received_principal=money(attempt.principal_amount),
                    reference=intent_id,
                    provider_charge_id=validated.latest_charge_id,
                    provider_event_id=f"reconcile:{intent_id}:succeeded",
                    verified_provider_fact=True,
                )
                result["confirmed"] += 1
                continue
            if status_value in cancelable:
                cancelled = cancel_intent(
                    attempt.provider_intent_id,
                    stripe_account=attempt.provider_account_id,
                )
                cancelled_validated = await validate_db048_stripe_payment_intent(
                    db=db,
                    payment_intent=cancelled,
                    trusted_provider_account_id=attempt.provider_account_id,
                    attempt=attempt,
                    allowed_statuses={"canceled"},
                )
                status_value = cancelled_validated.status
            if status_value in terminal_release:
                await fail_attempt(
                    db,
                    attempt_id=attempt.id,
                    tenant_id=attempt.tenant_id,
                    actor=None,
                    expected_attempt_version=attempt.version,
                    failure_code="provider_reservation_expired",
                    idempotency_key=f"stripe-reconcile:{attempt.provider_account_id}:{intent_id}:expired",
                    expired=True,
                )
                result["released"] += 1
            else:
                attempt.expires_at = now + timedelta(minutes=CARD_RECONCILE_RETRY_MINUTES)
                result["deferred"] += 1
        except SettlementDomainError as exc:
            if exc.code == "invoice_not_found":
                result["deferred"] += 1
                continue
            if exc.code != "provider_payment_mismatch":
                raise
            await _record_card_reconciliation_failure(
                db,
                attempt=attempt,
                code=exc.code,
                now=now,
            )
            result["deferred"] += 1
        except DB048ReconciliationError as exc:
            await _record_card_reconciliation_failure(
                db,
                attempt=attempt,
                code=str(exc),
                now=now,
            )
            result["deferred"] += 1
        except stripe.error.StripeError:
            deferred = (await db.execute(select(InvoicePaymentAttempt).where(
                InvoicePaymentAttempt.id == attempt_id,
            ).with_for_update())).scalar_one_or_none()
            if deferred and deferred.state == "pending":
                deferred.expires_at = now + timedelta(minutes=CARD_RECONCILE_RETRY_MINUTES)
            result["deferred"] += 1
    return result


async def process_db048_settlement_maintenance(
    *,
    session_factory: async_sessionmaker[AsyncSession] = AsyncSessionLocal,
) -> dict[str, int]:
    """Run bounded manual-expiry and provider-checked card reconciliation."""
    async with session_factory() as db:
        manual_expired = await expire_due_attempts(db, limit=100)
        card = await reconcile_due_card_attempts(db, limit=100)
        await db.commit()
    return {"manual_expired": manual_expired, **card}


def stripe_payout_equation(
    *,
    gross_receipts: Decimal,
    customer_card_fees: Decimal,
    card_fee_tax: Decimal,
    refunds: Decimal,
    disputes: Decimal,
    processor_fees: Decimal,
) -> Decimal:
    """Return the net deposit which the bank feed is allowed to match."""
    return money(
        money(gross_receipts)
        + money(customer_card_fees)
        + money(card_fee_tax)
        - money(refunds)
        - money(disputes)
        - money(processor_fees)
    )


def db048_qbo_invoice_payload(
    *,
    invoice: Invoice,
    qbo_customer_id: str,
    qbo_item_id: str,
    principal_total: Decimal,
    tenant_name: Optional[str] = None,
) -> dict[str, Any]:
    """Build the canonical A/R invoice excluding card surcharge money."""
    principal = money(principal_total)
    memo = quickbooks_invoice_memo(invoice, tenant_name=tenant_name)
    document_number = _qbo_invoice_document_number(invoice)
    return {
        "DocNumber": document_number,
        "CustomerRef": {"value": qbo_customer_id},
        "TxnDate": (invoice.created_at or datetime.now(timezone.utc)).date().isoformat(),
        "DueDate": invoice.due_date.date().isoformat() if invoice.due_date else None,
        "PrivateNote": memo,
        "CustomerMemo": {"value": memo},
        "Line": [{
            "Amount": float(principal),
            "Description": memo,
            "DetailType": "SalesItemLineDetail",
            "SalesItemLineDetail": {
                "ItemRef": {"value": qbo_item_id},
                "Qty": 1,
                "UnitPrice": float(principal),
            },
        }],
    }


def db048_qbo_payment_reference(
    *,
    attempt: Optional[InvoicePaymentAttempt],
    payment: Payment,
) -> str:
    """Choose the strongest CPA-facing trace that fits QBO PaymentRefNum."""
    reference: object = getattr(payment, "payment_number", "")
    if attempt is not None:
        provider = str(getattr(attempt, "provider", None) or "").strip()
        rail = str(getattr(attempt, "rail", None) or "").strip().lower()
        if (
            provider == "quickbooks_payments"
            and getattr(attempt, "provider_charge_id", None)
        ):
            reference = f"QBP {attempt.provider_charge_id}"
        elif provider == "stripe_connect" and getattr(attempt, "provider_charge_id", None):
            reference = f"Stripe {attempt.provider_charge_id}"
        elif (
            rail in {"zelle", "check", "ach"}
            and getattr(attempt, "provider_reference", None)
        ):
            provider_reference = str(attempt.provider_reference).strip()
            if rail == "zelle":
                parts = provider_reference.upper().split("-")
                invoice_part = next(
                    (part for part in parts if part.startswith("ETSINV")),
                    None,
                )
                if invoice_part:
                    part_index = parts.index(invoice_part)
                    amount_part = (
                        parts[part_index + 1]
                        if len(parts) > part_index + 1
                        else ""
                    )
                    invoice_suffix = invoice_part.removeprefix("ETSINV")
                    reference = " ".join(
                        segment
                        for segment in (
                            "Zelle",
                            invoice_suffix,
                            f"${amount_part}" if amount_part else "",
                        )
                        if segment
                    )
                else:
                    reference = (
                        provider_reference
                        if provider_reference.casefold().startswith(rail)
                        else f"Zelle {provider_reference}"
                    )
            else:
                reference = (
                    provider_reference
                    if provider_reference.casefold().startswith(rail)
                    else f"{rail.upper() if rail == 'ach' else rail.title()} "
                    f"{provider_reference}"
                )
    resolved = str(reference or "").strip()
    if not resolved:
        raise DB048ReconciliationError("QuickBooks payment reference is missing")
    return resolved[:21]


def db048_qbo_payment_memo(
    *,
    attempt: Optional[InvoicePaymentAttempt],
    payment: Payment,
    invoice: Invoice,
) -> str:
    """Return a concise memo a bookkeeper can understand without internal IDs."""
    provider = str(getattr(attempt, "provider", None) or "").strip()
    rail = str(
        getattr(attempt, "rail", None)
        or getattr(payment, "method", None)
        or "payment"
    ).strip().lower()
    if provider == "quickbooks_payments":
        label = "QuickBooks card payment"
    elif provider == "stripe_connect":
        label = "Stripe card payment"
    elif rail == "zelle":
        label = "Zelle payment"
    elif rail == "check":
        label = "Check payment"
    elif rail == "ach":
        label = "ACH payment"
    else:
        label = "Invoice payment"
    full_reference = db048_qbo_payment_reference(attempt=attempt, payment=payment)
    if attempt is not None:
        if provider == "quickbooks_payments" and getattr(
            attempt, "provider_charge_id", None
        ):
            full_reference = f"QBP {attempt.provider_charge_id}"
        elif provider == "stripe_connect" and getattr(
            attempt, "provider_charge_id", None
        ):
            full_reference = f"Stripe {attempt.provider_charge_id}"
        elif rail in {"zelle", "check", "ach"} and getattr(
            attempt, "provider_reference", None
        ):
            full_reference = str(attempt.provider_reference).strip()
    return (
        f"{label} for invoice {invoice.invoice_number}; "
        f"reference {full_reference}"
    )


def _qbo_payment_note_matches(
    note: object,
    *,
    attempt: InvoicePaymentAttempt,
    payment: Payment,
    invoice: Optional[Invoice],
    payment_id: Optional[str] = None,
) -> bool:
    """Accept current CPA-facing notes and legacy identity markers."""
    resolved = str(note or "")
    current_memo_matches = (
        resolved == db048_qbo_payment_memo(
            attempt=attempt,
            payment=payment,
            invoice=invoice,
        )
        if invoice is not None
        else resolved.endswith(
            f"reference {db048_qbo_payment_reference(attempt=attempt, payment=payment)}"
        )
    )
    return (
        current_memo_matches
        or f"attempt={attempt.id}" in resolved
        or (payment_id is not None and f"credit-source={payment_id}" in resolved)
    )


async def reconcile_qbo_payment_presentation(
    connection: QuickBooksConnection,
    *,
    qbo_payment_id: str,
    attempt: InvoicePaymentAttempt,
    payment: Payment,
    invoice: Invoice,
    qbo_customer_id: str,
    received_principal: Decimal,
) -> None:
    """Refresh only CPA-facing metadata on an existing validated QBO payment."""
    current = await _request(connection, "GET", f"payment/{qbo_payment_id}")
    qbo_payment = current.get("Payment") if isinstance(current, dict) else None
    if not isinstance(qbo_payment, dict) or str(qbo_payment.get("Id") or "") != str(
        qbo_payment_id
    ):
        raise DB048ReconciliationError("Existing QuickBooks payment could not be loaded")
    legacy_reference = str(getattr(payment, "payment_number", "") or "")[:21]
    expected_reference = db048_qbo_payment_reference(attempt=attempt, payment=payment)
    current_reference = str(qbo_payment.get("PaymentRefNum") or "")
    current_note = str(qbo_payment.get("PrivateNote") or "")
    prior_readable_note = (
        f"invoice {invoice.invoice_number}" in current_note
        and current_note.endswith(f"reference {current_reference}")
    )
    if (
        str((qbo_payment.get("CustomerRef") or {}).get("value") or "")
        != str(qbo_customer_id)
        or money(qbo_payment.get("TotalAmt")) != money(received_principal)
        or current_reference
        not in {
            expected_reference,
            legacy_reference,
            str(getattr(attempt, "provider_charge_id", "") or "")[:21],
            str(getattr(attempt, "provider_reference", "") or "")[:21],
        }
        or (
            not prior_readable_note
            and not _qbo_payment_note_matches(
                current_note,
                attempt=attempt,
                payment=payment,
                invoice=invoice,
                payment_id=qbo_payment_id,
            )
        )
    ):
        raise DB048ReconciliationError(
            "QuickBooks payment identity does not match the local receipt"
        )
    expected_note = db048_qbo_payment_memo(
        attempt=attempt,
        payment=payment,
        invoice=invoice,
    )
    if current_reference == expected_reference and str(
        qbo_payment.get("PrivateNote") or ""
    ) == expected_note:
        return
    sync_token = qbo_payment.get("SyncToken")
    if sync_token is None:
        raise DB048ReconciliationError(
            "Existing QuickBooks payment cannot be updated safely"
        )
    response = await _request(
        connection,
        "POST",
        "payment",
        params={
            "operation": "update",
            "requestid": _qbo_request_id("paymeta", attempt.id),
        },
        json={
            "Id": str(qbo_payment_id),
            "SyncToken": str(sync_token),
            "sparse": True,
            "PaymentRefNum": expected_reference,
            "PrivateNote": expected_note,
        },
    )
    updated = response.get("Payment") if isinstance(response, dict) else None
    if not isinstance(updated, dict) or str(updated.get("Id") or "") != str(
        qbo_payment_id
    ):
        raise QuickBooksAccountingError(
            "QuickBooks did not update the payment presentation"
        )


def db048_qbo_payment_payload(
    *,
    payment: Payment,
    invoice: Invoice,
    qbo_customer_id: str,
    qbo_invoice_id: str,
    principal_amount: Decimal,
    deposit_account: str,
    received_principal_amount: Optional[Decimal] = None,
    attempt: Optional[InvoicePaymentAttempt] = None,
    tenant_name: Optional[str] = None,
    customer_name: Optional[str] = None,
) -> dict[str, Any]:
    """Build one QBO receipt with only applied principal linked to A/R.

    A provider race can leave part of the customer's principal receipt
    unapplied.  QBO must still receive one Payment for the attempt: ``TotalAmt``
    is the full principal receipt, while the only allocation line is the amount
    applied to this invoice. Card surcharge and tax remain separate journal
    entries and never reduce A/R.
    """
    principal = money(principal_amount)
    received = money(
        received_principal_amount
        if received_principal_amount is not None
        else principal
    )
    if received < principal:
        raise DB048ReconciliationError(
            "QuickBooks payment receipt is smaller than its invoice allocation"
        )
    reference = db048_qbo_payment_reference(attempt=attempt, payment=payment)
    payload: dict[str, Any] = {
        "CustomerRef": {"value": qbo_customer_id},
        "TotalAmt": float(received),
        "PaymentRefNum": reference,
        "DepositToAccountRef": {"value": deposit_account},
        "PrivateNote": db048_qbo_payment_memo(
            attempt=attempt,
            payment=payment,
            invoice=invoice,
        ),
        "Line": [],
    }
    if principal > ZERO:
        payload["Line"] = [{
            "Amount": float(principal),
            "LinkedTxn": [{"TxnId": qbo_invoice_id, "TxnType": "Invoice"}],
        }]
    return payload


def db048_qbo_unapplied_payment_payload(
    *,
    payment: Payment,
    qbo_customer_id: str,
    amount: Decimal,
    deposit_account: str,
) -> dict[str, Any]:
    """Represent excess receipts as unapplied customer money, never revenue."""
    unapplied = money(amount)
    return {
        "CustomerRef": {"value": qbo_customer_id},
        "TotalAmt": float(unapplied),
        "PaymentRefNum": f"U-{payment.payment_number}"[:21],
        "DepositToAccountRef": {"value": deposit_account},
        "PrivateNote": "DB-048 unapplied customer overpayment pending refund or explicit credit consent",
        "Line": [],
    }


def db048_qbo_credit_application_payload(
    *,
    source_payment: dict[str, Any],
    applications: list[tuple[str, Decimal]],
) -> dict[str, Any]:
    """Link consented customer credit to invoices on its original QBO Payment.

    The receipt remains one customer Payment.  Applying store credit changes
    only its A/R allocation lines; it never creates income, a synthetic Credit
    Memo, or a second receipt.  Rebuilding all lines from the immutable local
    credit ledger also makes a worker replay deterministic.
    """
    payment_id = source_payment.get("Id")
    sync_token = source_payment.get("SyncToken")
    customer_ref = source_payment.get("CustomerRef")
    total_amount = money(source_payment.get("TotalAmt"))
    if not payment_id or sync_token is None or not customer_ref or total_amount <= ZERO:
        raise DB048ReconciliationError("QuickBooks unapplied payment identity is incomplete")

    by_invoice: dict[str, Decimal] = {}
    for invoice_id, amount in applications:
        invoice_id = str(invoice_id or "").strip()
        value = money(amount)
        if not invoice_id or value <= ZERO:
            raise DB048ReconciliationError("Customer credit application is invalid")
        by_invoice[invoice_id] = money(by_invoice.get(invoice_id, ZERO) + value)
    allocated = money(sum(by_invoice.values(), ZERO))
    if allocated > total_amount:
        raise DB048ReconciliationError("Customer credit applications exceed the original unapplied payment")

    payload: dict[str, Any] = {
        "Id": str(payment_id),
        "SyncToken": str(sync_token),
        "CustomerRef": customer_ref,
        "TotalAmt": float(total_amount),
        "Line": [
            {
                "Amount": float(by_invoice[invoice_id]),
                "LinkedTxn": [{"TxnId": invoice_id, "TxnType": "Invoice"}],
            }
            for invoice_id in sorted(by_invoice)
        ],
        "PrivateNote": (
            f"DB-048 credit-source={payment_id}; "
            "customer-approved store credit applications; no new receipt or revenue"
        ),
    }
    for key in (
        "PaymentRefNum",
        "DepositToAccountRef",
        "TxnDate",
        "PaymentMethodRef",
        "CurrencyRef",
        "ExchangeRate",
    ):
        if source_payment.get(key) is not None:
            payload[key] = source_payment[key]
    return payload


def db048_qbo_overpayment_refund_payload(
    *,
    refund: PaymentRefund,
    qbo_customer_id: str,
    receivable_account: str,
    source_account: str,
) -> dict[str, Any]:
    """Reverse unapplied customer money without touching sales income."""
    amount = money(refund.amount)
    document_number = f"R-{str(refund.id).replace('-', '')[:18]}"[:21]
    return {
        "DocNumber": document_number,
        "PrivateNote": "DB-048 refund of unapplied customer overpayment",
        "Line": [
            {
                "Amount": float(amount),
                "DetailType": "JournalEntryLineDetail",
                "JournalEntryLineDetail": {
                    "PostingType": "Debit",
                    "AccountRef": {"value": receivable_account},
                    "Entity": {"Type": "Customer", "EntityRef": {"value": qbo_customer_id}},
                },
            },
            {
                "Amount": float(amount),
                "DetailType": "JournalEntryLineDetail",
                "JournalEntryLineDetail": {
                    "PostingType": "Credit",
                    "AccountRef": {"value": source_account},
                },
            },
        ],
    }


def db048_qbo_adjustment_payloads(
    *,
    attempt: InvoicePaymentAttempt,
    payment: Payment,
    mappings: dict[str, Optional[str]],
) -> list[tuple[str, dict[str, Any]]]:
    """Return separate card-fee/tax and processor-expense journal entries."""
    clearing = (
        mappings.get("stripe_clearing_account")
        if attempt.provider == "stripe_connect"
        else mappings.get("qbp_clearing_account")
    )
    payloads: list[tuple[str, dict[str, Any]]] = []
    fee = money(attempt.applied_card_fee_amount)
    fee_tax = money(attempt.applied_card_fee_tax_amount)
    if fee + fee_tax > ZERO:
        if not clearing or not mappings.get("card_fee_income_account") or not mappings.get("sales_tax_liability_account"):
            raise DB048ReconciliationError("Card fee accounting mappings are incomplete")
        lines = [{
            "Amount": float(fee + fee_tax),
            "DetailType": "JournalEntryLineDetail",
            "JournalEntryLineDetail": {"PostingType": "Debit", "AccountRef": {"value": clearing}},
        }]
        if fee > ZERO:
            lines.append({
                "Amount": float(fee),
                "DetailType": "JournalEntryLineDetail",
                "JournalEntryLineDetail": {
                    "PostingType": "Credit",
                    "AccountRef": {"value": mappings["card_fee_income_account"]},
                },
            })
        if fee_tax > ZERO:
            lines.append({
                "Amount": float(fee_tax),
                "DetailType": "JournalEntryLineDetail",
                "JournalEntryLineDetail": {
                    "PostingType": "Credit",
                    "AccountRef": {"value": mappings["sales_tax_liability_account"]},
                },
            })
        payloads.append((f"F-{payment.payment_number}"[:21], {
            "DocNumber": f"F-{payment.payment_number}"[:21],
            "PrivateNote": "DB-048 customer card fee and fee tax",
            "Line": lines,
        }))
    # Stripe's authoritative processing fee arrives on the payout balance
    # transaction. Booking an estimated/intent-time value here and the actual
    # payout fee later would double the expense and strand clearing. QBP may
    # eventually supply a captured fee through its native/import contract, but
    # its production gate remains dormant.
    processor_fee = (
        ZERO
        if attempt.provider == "stripe_connect"
        else money(attempt.processor_fee_amount)
    )
    if processor_fee > ZERO:
        if not clearing or not mappings.get("processor_fee_expense_account"):
            raise DB048ReconciliationError("Processor fee accounting mappings are incomplete")
        payloads.append((f"PF-{payment.payment_number}"[:21], {
            "DocNumber": f"PF-{payment.payment_number}"[:21],
            "PrivateNote": "DB-048 provider processing expense",
            "Line": [
                {
                    "Amount": float(processor_fee),
                    "DetailType": "JournalEntryLineDetail",
                    "JournalEntryLineDetail": {
                        "PostingType": "Debit",
                        "AccountRef": {"value": mappings["processor_fee_expense_account"]},
                    },
                },
                {
                    "Amount": float(processor_fee),
                    "DetailType": "JournalEntryLineDetail",
                    "JournalEntryLineDetail": {
                        "PostingType": "Credit", "AccountRef": {"value": clearing},
                    },
                },
            ],
        }))
    return payloads


async def _sync_db048_unearned_surcharge(
    envelope: AccountingEnvelope,
    *,
    qbo_customer_id: str,
) -> Optional[str]:
    """Book refundable, unearned card surcharge as customer A/R credit."""
    principal_excess = max(
        ZERO,
        money(envelope.attempt.received_amount or envelope.attempt.principal_amount)
        - money(envelope.attempt.applied_principal_amount),
    )
    unearned = max(
        ZERO,
        money(envelope.attempt.unapplied_amount) - principal_excess,
    )
    if unearned == ZERO:
        return None
    mappings = envelope.link.account_mapping_snapshot or {}
    clearing = mappings.get("stripe_clearing_account")
    if not clearing:
        raise DB048ReconciliationError("Stripe clearing mapping is missing")
    receivable_rows = await _query(
        envelope.connection,
        "select * from Account where AccountType = 'Accounts Receivable' maxresults 1",
    )
    if not receivable_rows or not receivable_rows[0].get("Id"):
        raise DB048ReconciliationError(
            "QuickBooks Accounts Receivable account is unavailable", retryable=True,
        )
    document_number = f"UF-{envelope.payment.payment_number}"[:21]
    existing = await _qbo_find_by_doc_number(
        envelope.connection, "JournalEntry", document_number,
    )
    if existing and existing.get("Id"):
        return str(existing["Id"])
    response = await _request(
        envelope.connection,
        "POST",
        "journalentry",
        json={
            "DocNumber": document_number,
            "PrivateNote": (
                "DB-048 refundable unearned card surcharge held as unapplied customer money"
            ),
            "Line": [
                {
                    "Amount": float(unearned),
                    "DetailType": "JournalEntryLineDetail",
                    "JournalEntryLineDetail": {
                        "PostingType": "Debit",
                        "AccountRef": {"value": clearing},
                    },
                },
                {
                    "Amount": float(unearned),
                    "DetailType": "JournalEntryLineDetail",
                    "JournalEntryLineDetail": {
                        "PostingType": "Credit",
                        "AccountRef": {"value": str(receivable_rows[0]["Id"])},
                        "Entity": {
                            "Type": "Customer",
                            "EntityRef": {"value": qbo_customer_id},
                        },
                    },
                },
            ],
        },
        params={"requestid": _qbo_request_id("unearned", envelope.attempt.id)},
    )
    journal = response.get("JournalEntry") if isinstance(response, dict) else None
    if not isinstance(journal, dict) or not journal.get("Id"):
        raise QuickBooksAccountingError(
            "QuickBooks did not return the unearned surcharge adjustment"
        )
    return str(journal["Id"])


async def load_accounting_envelope(
    db: AsyncSession,
    event: ProviderOutboxEvent,
) -> AccountingEnvelope:
    """Resolve and validate the complete tenant envelope before provider I/O."""
    payload = event.payload or {}
    try:
        link_id = UUID(str(payload["accounting_link_id"]))
    except (KeyError, TypeError, ValueError) as exc:
        raise DB048ReconciliationError("Accounting outbox envelope is invalid") from exc
    link = (await db.execute(select(PaymentAccountingLink).where(
        PaymentAccountingLink.id == link_id,
        PaymentAccountingLink.tenant_id == event.tenant_id,
    ))).scalar_one_or_none()
    if not link or link.sync_state == "synced":
        if link and link.sync_state == "synced":
            raise DB048ReconciliationError("Accounting operation is already synchronized")
        raise DB048ReconciliationError("Accounting link was not found")
    attempt = (await db.execute(select(InvoicePaymentAttempt).where(
        InvoicePaymentAttempt.id == link.attempt_id,
        InvoicePaymentAttempt.tenant_id == event.tenant_id,
        InvoicePaymentAttempt.invoice_id == link.invoice_id,
        InvoicePaymentAttempt.state.in_(["confirmed", "refunded", "reversed"]),
    ))).scalar_one_or_none()
    if not attempt or attempt.payment_id is None:
        raise DB048ReconciliationError("Confirmed allocation was not found")
    payment = (await db.execute(select(Payment).where(
        Payment.id == attempt.payment_id,
        Payment.tenant_id == event.tenant_id,
        Payment.invoice_id == attempt.invoice_id,
        Payment.invoice_payment_attempt_id == attempt.id,
    ))).scalar_one_or_none()
    invoice = (await db.execute(select(Invoice).where(
        Invoice.id == attempt.invoice_id,
        Invoice.tenant_id == event.tenant_id,
    ))).scalar_one_or_none()
    if not payment or not invoice:
        raise DB048ReconciliationError("Accounting source records do not match")
    order = (await db.execute(select(RepairOrder).where(
        RepairOrder.id == invoice.repair_order_id,
        RepairOrder.tenant_id == event.tenant_id,
    ))).scalar_one_or_none()
    customer = (await db.execute(select(Customer).where(
        Customer.id == (order.customer_id if order else None),
        Customer.tenant_id == event.tenant_id,
    ))).scalar_one_or_none()
    tenant = await db.get(Tenant, event.tenant_id)
    config = (await db.execute(select(TenantPaymentProviderConfiguration).where(
        TenantPaymentProviderConfiguration.tenant_id == event.tenant_id,
        TenantPaymentProviderConfiguration.version == attempt.provider_configuration_version,
    ))).scalar_one_or_none()
    connection = (await db.execute(select(QuickBooksConnection).where(
        QuickBooksConnection.tenant_id == event.tenant_id,
        QuickBooksConnection.deleted_at.is_(None),
        QuickBooksConnection.status == "connected",
        QuickBooksConnection.realm_id == link.qbo_realm_snapshot,
    ))).scalar_one_or_none()
    settlement = (await db.execute(select(InvoiceSettlement).where(
        InvoiceSettlement.id == attempt.settlement_id,
        InvoiceSettlement.tenant_id == event.tenant_id,
        InvoiceSettlement.invoice_id == invoice.id,
    ))).scalar_one_or_none()
    if (
        not tenant or not order or not customer or not config or not connection
        or not connection.realm_id or not settlement
        or not config.qbo_realm_snapshot
        or link.qbo_realm_snapshot != config.qbo_realm_snapshot
        or connection.realm_id != config.qbo_realm_snapshot
    ):
        raise DB048ReconciliationError("Tenant accounting configuration is unavailable", retryable=True)
    if link.owning_writer != config.writer_strategy:
        raise DB048ReconciliationError("Accounting writer ownership changed")
    if payload.get("attempt_id") and str(payload["attempt_id"]) != str(attempt.id):
        raise DB048ReconciliationError("Accounting attempt envelope does not match")
    if link.financial_object_type == "payment_reversal":
        # The first accounting link owns the QBO unapplied Payment identity.
        # Resolve it at delivery time rather than snapshotting it at reversal
        # creation, because a provider dispute may arrive while the original
        # accounting outbox is still retrying.
        source_link = await db.scalar(select(PaymentAccountingLink).where(
            PaymentAccountingLink.tenant_id == event.tenant_id,
            PaymentAccountingLink.attempt_id == attempt.id,
            PaymentAccountingLink.financial_object_type == "invoice_payment",
            PaymentAccountingLink.operation_version == 1,
        ))
        if source_link and source_link.provider_deposit_id:
            link.provider_deposit_id = source_link.provider_deposit_id
    if payload.get("invoice_id") and str(payload["invoice_id"]) != str(invoice.id):
        raise DB048ReconciliationError("Accounting invoice envelope does not match")
    refund = None
    if event.event_type == REFUND_ACCOUNTING_EVENT:
        refund = (await db.execute(select(PaymentRefund).where(
            PaymentRefund.id == link.refund_id,
            PaymentRefund.tenant_id == event.tenant_id,
            PaymentRefund.source_attempt_id == attempt.id,
            PaymentRefund.state == "succeeded",
        ))).scalar_one_or_none()
        if not refund:
            raise DB048ReconciliationError("Refund accounting source was not found")
    dispute = None
    if event.event_type in {DISPUTE_ACCOUNTING_EVENT, DISPUTE_RECOVERY_ACCOUNTING_EVENT}:
        try:
            dispute_id = UUID(str(payload["dispute_id"]))
        except (KeyError, TypeError, ValueError) as exc:
            raise DB048ReconciliationError("Dispute accounting source is invalid") from exc
        dispute = await db.scalar(select(PaymentProviderDispute).where(
            PaymentProviderDispute.id == dispute_id,
            PaymentProviderDispute.tenant_id == event.tenant_id,
            PaymentProviderDispute.attempt_id == attempt.id,
            PaymentProviderDispute.provider_account_id == attempt.provider_account_id,
            PaymentProviderDispute.provider_charge_id == attempt.provider_charge_id,
        ))
        expected_state = "won" if event.event_type == DISPUTE_RECOVERY_ACCOUNTING_EVENT else None
        if not dispute or (expected_state and dispute.state != expected_state):
            raise DB048ReconciliationError("Dispute accounting source was not found")
    return AccountingEnvelope(
        event.id, tenant, link, attempt, payment, invoice, customer,
        connection, config, settlement, refund, dispute,
    )


async def load_credit_accounting_envelope(
    db: AsyncSession,
    event: ProviderOutboxEvent,
) -> CreditAccountingEnvelope:
    """Resolve a credit application back to its one original customer receipt."""
    payload = event.payload or {}
    try:
        link_id = UUID(str(payload["accounting_link_id"]))
        application_id = UUID(str(payload["credit_entry_id"]))
    except (KeyError, TypeError, ValueError) as exc:
        raise DB048ReconciliationError("Credit accounting outbox envelope is invalid") from exc
    link = await db.scalar(select(PaymentAccountingLink).where(
        PaymentAccountingLink.id == link_id,
        PaymentAccountingLink.tenant_id == event.tenant_id,
        PaymentAccountingLink.financial_object_type == "customer_credit_application",
        PaymentAccountingLink.financial_object_id == application_id,
    ))
    if not link:
        raise DB048ReconciliationError("Credit accounting link was not found")
    if link.sync_state == "synced":
        raise DB048ReconciliationError("Credit accounting operation is already synchronized")
    application = await db.scalar(select(CustomerCreditEntry).where(
        CustomerCreditEntry.id == application_id,
        CustomerCreditEntry.tenant_id == event.tenant_id,
        CustomerCreditEntry.entry_type == "applied",
        CustomerCreditEntry.target_invoice_id == link.invoice_id,
    ))
    origin = await db.scalar(select(CustomerCreditEntry).where(
        CustomerCreditEntry.id == (application.source_entry_id if application else None),
        CustomerCreditEntry.tenant_id == event.tenant_id,
        CustomerCreditEntry.entry_type == "issued",
    ).with_for_update())
    overpayment = await db.scalar(select(PaymentOverpayment).where(
        PaymentOverpayment.id == (origin.origin_overpayment_id if origin else None),
        PaymentOverpayment.tenant_id == event.tenant_id,
        PaymentOverpayment.customer_id == (origin.customer_id if origin else None),
    ))
    source_attempt = await db.scalar(select(InvoicePaymentAttempt).where(
        InvoicePaymentAttempt.id == (overpayment.source_attempt_id if overpayment else None),
        InvoicePaymentAttempt.tenant_id == event.tenant_id,
        InvoicePaymentAttempt.state == "confirmed",
    ))
    source_payment = await db.scalar(select(Payment).where(
        Payment.id == (source_attempt.payment_id if source_attempt else None),
        Payment.tenant_id == event.tenant_id,
        Payment.invoice_payment_attempt_id == (source_attempt.id if source_attempt else None),
    ))
    source_link = await db.scalar(select(PaymentAccountingLink).where(
        PaymentAccountingLink.tenant_id == event.tenant_id,
        PaymentAccountingLink.attempt_id == (source_attempt.id if source_attempt else None),
        PaymentAccountingLink.financial_object_type == "invoice_payment",
        PaymentAccountingLink.operation_version == 1,
    ))
    target_invoice = await db.scalar(select(Invoice).where(
        Invoice.id == link.invoice_id,
        Invoice.tenant_id == event.tenant_id,
    ))
    target_order = await db.scalar(select(RepairOrder).where(
        RepairOrder.id == (target_invoice.repair_order_id if target_invoice else None),
        RepairOrder.tenant_id == event.tenant_id,
    ))
    target_customer = await db.scalar(select(Customer).where(
        Customer.id == (target_order.customer_id if target_order else None),
        Customer.tenant_id == event.tenant_id,
    ))
    target_settlement = await db.scalar(select(InvoiceSettlement).where(
        InvoiceSettlement.invoice_id == (target_invoice.id if target_invoice else None),
        InvoiceSettlement.tenant_id == event.tenant_id,
        InvoiceSettlement.customer_id == (origin.customer_id if origin else None),
    ))
    config = await db.scalar(select(TenantPaymentProviderConfiguration).where(
        TenantPaymentProviderConfiguration.tenant_id == event.tenant_id,
        TenantPaymentProviderConfiguration.version == (
            source_attempt.provider_configuration_version if source_attempt else None
        ),
    ))
    connection = await db.scalar(select(QuickBooksConnection).where(
        QuickBooksConnection.tenant_id == event.tenant_id,
        QuickBooksConnection.deleted_at.is_(None),
        QuickBooksConnection.status == "connected",
        QuickBooksConnection.realm_id == link.qbo_realm_snapshot,
    ))
    tenant = await db.get(Tenant, event.tenant_id)
    if not all((application, origin, overpayment, source_attempt, source_payment,
                source_link, target_invoice, target_order, target_customer,
                target_settlement, config, connection, tenant)):
        raise DB048ReconciliationError("Credit accounting source records do not match")
    if origin.customer_id != target_customer.id or application.customer_id != origin.customer_id:
        raise DB048ReconciliationError("Credit accounting customer identity does not match")
    if source_link.sync_state != "synced" or not source_link.provider_deposit_id:
        raise DB048ReconciliationError(
            "Original unapplied QuickBooks payment is not synchronized yet", retryable=True,
        )
    if link.owning_writer != config.writer_strategy or source_link.owning_writer != config.writer_strategy:
        raise DB048ReconciliationError("Accounting writer ownership changed")
    if (
        not connection.realm_id
        or not config.qbo_realm_snapshot
        or link.qbo_realm_snapshot != config.qbo_realm_snapshot
        or source_link.qbo_realm_snapshot != config.qbo_realm_snapshot
        or connection.realm_id != config.qbo_realm_snapshot
    ):
        raise DB048ReconciliationError("Tenant accounting configuration is unavailable", retryable=True)
    return CreditAccountingEnvelope(
        event.id,
        tenant,
        link,
        application,
        origin,
        overpayment,
        source_attempt,
        source_payment,
        source_link,
        target_invoice,
        target_customer,
        target_settlement,
        connection,
        config,
    )


async def _qbo_find_by_doc_number(
    connection: QuickBooksConnection,
    entity: str,
    document_number: str,
) -> Optional[dict[str, Any]]:
    rows = await _query(
        connection,
        f"select * from {entity} where DocNumber = '{_escape_query(document_number)}' maxresults 1",
    )
    return rows[0] if rows else None


async def _resolve_qbo_account_reference(
    connection: QuickBooksConnection,
    configured_reference: object,
) -> str:
    """Resolve a tenant mapping to the account ID required by QBO refs.

    Existing DB-048 configuration accepts the account picker value as a
    string, and early local configurations stored the visible QBO account name
    rather than its provider ID. QBO write payloads require the ID in the
    ``value`` field, so resolve both representations against the active realm
    before any accounting mutation.
    """
    reference = str(configured_reference or "").strip()
    if not reference:
        raise DB048ReconciliationError("QuickBooks account mapping is missing")

    if reference.isdigit():
        rows = await _query(
            connection,
            f"select * from Account where Id = '{_escape_query(reference)}' maxresults 1",
        )
    else:
        rows = await _query(
            connection,
            f"select * from Account where Name = '{_escape_query(reference)}' maxresults 2",
        )
    matches = [
        row for row in rows
        if row.get("Id")
        and row.get("Active") is not False
        and (
            str(row.get("Id")) == reference
            if reference.isdigit()
            else str(row.get("Name") or "") == reference
        )
    ]
    if len(matches) != 1:
        raise DB048ReconciliationError(
            f"QuickBooks account mapping '{reference}' was not found in the connected company"
        )
    return str(matches[0]["Id"])


def _qbo_request_id(kind: str, identity: object) -> str:
    """Stable Intuit requestid used as the provider-side idempotency fence."""
    digest = hashlib.sha256(f"db048:{kind}:{identity}".encode()).hexdigest()[:32]
    return f"db048-{kind[:8]}-{digest}"[:50]


def _qbo_invoice_document_number(invoice: Invoice) -> str:
    document_number = str(invoice.invoice_number or "")
    if not document_number or len(document_number) > 21:
        raise DB048ReconciliationError(
            "Invoice number is not valid for QuickBooks synchronization"
        )
    return document_number


def _validate_qbo_invoice_identity(
    qbo_invoice: dict[str, Any],
    *,
    qbo_customer_id: str,
    invoice: Invoice,
    discovered_by_doc_number: bool,
    tenant_name: Optional[str] = None,
) -> None:
    expected_doc_number = _qbo_invoice_document_number(invoice)
    actual_doc_number = str(qbo_invoice.get("DocNumber") or "")
    if actual_doc_number != expected_doc_number:
        raise DB048ReconciliationError(
            "Existing QuickBooks invoice number does not match the local invoice"
        )
    customer_ref = qbo_invoice.get("CustomerRef") or {}
    if str(customer_ref.get("value") or "") != str(qbo_customer_id):
        raise DB048ReconciliationError(
            "Existing QuickBooks invoice belongs to a different customer"
        )
    private_note = str(qbo_invoice.get("PrivateNote") or "")
    # A locally persisted QBO ID may predate DB-048 and can be upgraded only
    # after both invoice number and customer identity are validated. A
    # DocNumber-only discovery must additionally carry either the current
    # shop-facing memo or the legacy DB-048 marker.
    expected_memo = quickbooks_invoice_memo(invoice, tenant_name=tenant_name)
    legacy_marker = f"DB-048 invoice={invoice.id}; principal-only A/R"
    if (
        discovered_by_doc_number
        and expected_memo not in private_note
        and legacy_marker not in private_note
    ):
        raise DB048ReconciliationError(
            "QuickBooks invoice number collides with an unrelated record"
        )


async def _ensure_db048_qbo_invoice(
    *,
    connection: QuickBooksConnection,
    invoice: Invoice,
    customer: Customer,
    principal_total: Decimal,
    tenant_name: Optional[str] = None,
) -> tuple[str, str]:
    """Return canonical customer/invoice IDs for principal-only DB-048 A/R."""
    from app.services.invoice_accounting_policy import require_exportable_invoice
    await require_exportable_invoice(invoice)
    # Every legacy caller (principal sync, credit target, dispute) must respect
    # the persisted composition. Never replace earned gross fee lines with a
    # principal-only payload simply because a different entry point ran.
    from sqlalchemy import inspect
    from sqlalchemy.ext.asyncio import async_object_session
    from app.services.db048_qbo_gross_accounting import is_gross, ensure_gross_invoice
    if inspect(invoice, raiseerr=False) is not None:
        attached_db = async_object_session(invoice)
        if attached_db is not None:
            attached_settlement = await attached_db.scalar(select(InvoiceSettlement).where(
                InvoiceSettlement.invoice_id == invoice.id,
                InvoiceSettlement.tenant_id == invoice.tenant_id,
            ))
            if attached_settlement is not None and is_gross(attached_settlement):
                return await ensure_gross_invoice(attached_db, connection=connection,
                    invoice=invoice, customer=customer, settlement=attached_settlement,
                    tenant_name=tenant_name)
    principal = money(principal_total)
    customer_id = await ensure_customer(
        connection,
        customer,
        tenant_name=tenant_name,
    )
    qbo_invoice_id = invoice.quickbooks_invoice_id
    if qbo_invoice_id:
        try:
            current = await _request(connection, "GET", f"invoice/{qbo_invoice_id}")
        except QuickBooksAccountingError as exc:
            # QBO entity IDs are company/realm scoped. A tenant can reconnect
            # a different sandbox or company while the local invoice still
            # carries the previous realm's ID. Only an explicit provider
            # missing/invalid-ID response may clear that stale identity; all
            # transient provider failures must fail closed to avoid duplicates.
            if exc.status_code not in {400, 404}:
                raise
            invoice.quickbooks_invoice_id = None
            qbo_invoice_id = None
            current = None
        if current is not None:
            current_invoice = current.get("Invoice") if isinstance(current, dict) else None
            if not isinstance(current_invoice, dict):
                raise DB048ReconciliationError("Existing QBO invoice could not be loaded")
            _validate_qbo_invoice_identity(
                current_invoice,
                qbo_customer_id=customer_id,
                invoice=invoice,
                discovered_by_doc_number=False,
                tenant_name=tenant_name,
            )
            expected_memo = quickbooks_invoice_memo(
                invoice,
                tenant_name=tenant_name,
            )
            needs_db048_upgrade = (
                money(current_invoice.get("TotalAmt")) != principal
                or str(current_invoice.get("PrivateNote") or "") != expected_memo
            )
            if needs_db048_upgrade:
                sync_token = current_invoice.get("SyncToken")
                if sync_token is None:
                    raise DB048ReconciliationError("Existing QBO invoice cannot be reconciled to DB-048 principal A/R")
                item_id = await _ensure_service_item(connection)
                payload = db048_qbo_invoice_payload(
                    invoice=invoice,
                    qbo_customer_id=customer_id,
                    qbo_item_id=item_id,
                    principal_total=principal,
                    tenant_name=tenant_name,
                )
                payload.update({"Id": str(qbo_invoice_id), "SyncToken": str(sync_token)})
                response = await _request(
                    connection,
                    "POST",
                    "invoice?operation=update",
                    json=payload,
                    params={"requestid": _qbo_request_id("invoice", invoice.id)},
                )
                updated = response.get("Invoice") if isinstance(response, dict) else None
                if not isinstance(updated, dict) or str(updated.get("Id")) != str(qbo_invoice_id):
                    raise QuickBooksAccountingError("QuickBooks did not reconcile the DB-048 principal invoice")
            return customer_id, str(qbo_invoice_id)
        # An explicit invalid/missing-ID response continues through the
        # current-realm DocNumber collision fence and deterministic create path.

    existing_invoice = await _qbo_find_by_doc_number(
        connection, "Invoice", _qbo_invoice_document_number(invoice),
    )
    if existing_invoice:
        _validate_qbo_invoice_identity(
            existing_invoice,
            qbo_customer_id=customer_id,
            invoice=invoice,
            discovered_by_doc_number=True,
            tenant_name=tenant_name,
        )
        qbo_invoice_id = str(existing_invoice["Id"])
        expected_memo = quickbooks_invoice_memo(
            invoice,
            tenant_name=tenant_name,
        )
        if (
            money(existing_invoice.get("TotalAmt")) != principal
            or str(existing_invoice.get("PrivateNote") or "") != expected_memo
        ):
            sync_token = existing_invoice.get("SyncToken")
            if sync_token is None:
                raise DB048ReconciliationError("Existing QBO invoice cannot be reconciled to DB-048 principal A/R")
            item_id = await _ensure_service_item(connection)
            payload = db048_qbo_invoice_payload(
                invoice=invoice,
                qbo_customer_id=customer_id,
                qbo_item_id=item_id,
                principal_total=principal,
                tenant_name=tenant_name,
            )
            payload.update({"Id": qbo_invoice_id, "SyncToken": str(sync_token)})
            response = await _request(
                connection,
                "POST",
                "invoice?operation=update",
                json=payload,
                params={"requestid": _qbo_request_id("invoice", invoice.id)},
            )
            updated = response.get("Invoice") if isinstance(response, dict) else None
            if not isinstance(updated, dict) or str(updated.get("Id")) != qbo_invoice_id:
                raise QuickBooksAccountingError("QuickBooks did not reconcile the DB-048 principal invoice")
    else:
        item_id = await _ensure_service_item(connection)
        response = await _request(
            connection,
            "POST",
            "invoice",
            json=db048_qbo_invoice_payload(
                invoice=invoice,
                qbo_customer_id=customer_id,
                qbo_item_id=item_id,
                principal_total=principal,
                tenant_name=tenant_name,
            ),
            params={"requestid": _qbo_request_id("invoice", invoice.id)},
        )
        qbo_invoice = response.get("Invoice") if isinstance(response, dict) else None
        if not isinstance(qbo_invoice, dict) or not qbo_invoice.get("Id"):
            raise QuickBooksAccountingError("QuickBooks did not return the DB-048 invoice")
        qbo_invoice_id = str(qbo_invoice["Id"])
    invoice.quickbooks_invoice_id = qbo_invoice_id
    invoice.quickbooks_sync_status = "synced"
    invoice.quickbooks_synced_at = datetime.now(timezone.utc)
    invoice.quickbooks_sync_error = None
    return customer_id, qbo_invoice_id


async def sync_db048_principal_invoice(
    *,
    connection: QuickBooksConnection,
    invoice: Invoice,
    customer: Customer,
    settlement: InvoiceSettlement,
) -> str:
    """Synchronize the one canonical QBO invoice using DB-048 principal A/R."""
    _customer_id, qbo_invoice_id = await _ensure_db048_qbo_invoice(
        connection=connection,
        invoice=invoice,
        customer=customer,
        principal_total=settlement.principal_total,
    )
    return qbo_invoice_id


def _fee_journal_semantics(payload: dict[str, Any]) -> tuple:
    """Ignore provider metadata, never ignore monetary or posting identity."""
    currency = payload.get("CurrencyRef")
    if currency is not None and (not isinstance(currency, dict) or currency.get("value") != "USD"):
        raise DB048ReconciliationError("Customer fee journal currency conflict")
    if payload.get("ExchangeRate") is not None:
        try:
            rate = Decimal(str(payload["ExchangeRate"]))
        except (InvalidOperation, ValueError):
            raise DB048ReconciliationError("Customer fee journal exchange rate conflict")
        if not rate.is_finite() or rate != Decimal("1"):
            raise DB048ReconciliationError("Customer fee journal exchange rate conflict")
    lines = []
    raw_lines = payload.get("Line")
    if not isinstance(raw_lines, list):
        raise DB048ReconciliationError("Customer fee journal contents conflict")
    for line in raw_lines:
        if not isinstance(line, dict):
            raise DB048ReconciliationError("Customer fee journal contents conflict")
        detail = line.get("JournalEntryLineDetail") or {}
        if not isinstance(detail, dict) or not isinstance(detail.get("AccountRef"), dict):
            raise DB048ReconciliationError("Customer fee journal contents conflict")
        if line.get("DetailType") != "JournalEntryLineDetail" or detail.get("Entity"):
            raise DB048ReconciliationError("Customer fee journal contents conflict")
        lines.append((str(detail.get("PostingType") or ""),
                      str((detail.get("AccountRef") or {}).get("value") or ""),
                      money(line.get("Amount"))))
    return (payload.get("DocNumber"), payload.get("PrivateNote"), sorted(lines))


def _validate_adjustment_owner(envelope: AccountingEnvelope) -> None:
    realm = getattr(envelope.link, "qbo_realm_snapshot", None)
    if not realm or realm != getattr(envelope.connection, "realm_id", None):
        raise DB048ReconciliationError("Customer fee journal realm mismatch")
    if (envelope.link.tenant_id != envelope.attempt.tenant_id
            or envelope.link.tenant_id != envelope.connection.tenant_id
            or envelope.link.attempt_id != envelope.attempt.id):
        raise DB048ReconciliationError("Customer fee journal ownership mismatch")


def _validate_customer_fee_identity(envelope: AccountingEnvelope) -> None:
    customer_fee = money(envelope.attempt.applied_card_fee_amount) + money(envelope.attempt.applied_card_fee_tax_amount)
    if customer_fee == ZERO and getattr(envelope.link, "provider_fee_journal_id", None):
        raise DB048ReconciliationError("Customer fee journal exists for a zero fee")


async def _sync_db048_adjustment_journals(envelope: AccountingEnvelope) -> None:
    _validate_customer_fee_identity(envelope)
    payloads = db048_qbo_adjustment_payloads(
        attempt=envelope.attempt, payment=envelope.payment,
        mappings=envelope.link.account_mapping_snapshot or {},
    )
    if not payloads:
        return
    _validate_adjustment_owner(envelope)
    for document_number, payload in payloads:
        is_customer_fee = document_number.startswith("F-")
        if is_customer_fee:
            payload["PrivateNote"] += f"; attempt={envelope.attempt.id}"
        for line in payload["Line"]:
            ref = line["JournalEntryLineDetail"]["AccountRef"]
            ref["value"] = await _resolve_qbo_account_reference(envelope.connection, ref["value"])
        saved_id = getattr(envelope.link, "provider_fee_journal_id", None) if is_customer_fee else None
        if saved_id:
            result = await _request(envelope.connection, "GET", f"journalentry/{saved_id}")
            existing = result.get("JournalEntry") if isinstance(result, dict) else None
            if not isinstance(existing, dict) or str(existing.get("Id")) != saved_id:
                raise DB048ReconciliationError("Customer fee journal identity conflict")
        else:
            rows = await _query(envelope.connection,
                f"select * from JournalEntry where DocNumber = '{_escape_query(document_number)}' maxresults 2")
            if len(rows) > 1:
                raise DB048ReconciliationError("Customer fee journal identity is ambiguous")
            existing = rows[0] if rows else None
        if existing:
            if not existing.get("Id") or _fee_journal_semantics(existing) != _fee_journal_semantics(payload):
                raise DB048ReconciliationError("Customer fee journal contents conflict")
            journal_id = str(existing["Id"])
        else:
            response = await _request(envelope.connection, "POST", "journalentry", json=payload,
                params={"requestid": _qbo_request_id("journal", document_number)})
            journal = response.get("JournalEntry") if isinstance(response, dict) else None
            if not isinstance(journal, dict) or not journal.get("Id"):
                raise QuickBooksAccountingError("QuickBooks did not return the DB-048 adjustment")
            if _fee_journal_semantics(journal) != _fee_journal_semantics(payload):
                raise DB048ReconciliationError("Customer fee journal response contents conflict")
            journal_id = str(journal["Id"])
        if is_customer_fee:
            envelope.link.provider_fee_journal_id = journal_id


async def sync_db048_payment(envelope: AccountingEnvelope) -> str:
    """Create principal-only A/R and one full-principal receipt, exactly once."""
    _validate_customer_fee_identity(envelope)
    if money(envelope.attempt.applied_card_fee_amount) + money(envelope.attempt.applied_card_fee_tax_amount) > ZERO:
        _validate_adjustment_owner(envelope)
    principal_total = money(envelope.settlement.principal_total)
    customer_id, qbo_invoice_id = await _ensure_db048_qbo_invoice(
        connection=envelope.connection,
        invoice=envelope.invoice,
        customer=envelope.customer,
        principal_total=principal_total,
        tenant_name=envelope.tenant.name,
    )

    mappings = envelope.link.account_mapping_snapshot or {}
    if envelope.attempt.provider == "stripe_connect":
        deposit_account = mappings.get("stripe_clearing_account")
    elif envelope.attempt.provider == "quickbooks_payments":
        deposit_account = mappings.get("qbp_clearing_account")
    elif envelope.attempt.rail == "check":
        deposit_account = mappings.get("check_deposit_account")
    else:
        deposit_account = mappings.get("zelle_ach_account")
    if not deposit_account:
        raise DB048ReconciliationError("Payment deposit account mapping is missing")
    deposit_account = await _resolve_qbo_account_reference(
        envelope.connection,
        deposit_account,
    )

    receipt_principal = money(
        envelope.attempt.received_amount
        if envelope.attempt.received_amount is not None
        else envelope.attempt.principal_amount
    )
    applied_principal = money(envelope.attempt.applied_principal_amount)
    if receipt_principal < applied_principal or receipt_principal <= ZERO:
        raise DB048ReconciliationError("DB-048 payment principal receipt is invalid")
    payment_id: Optional[str] = envelope.payment.quickbooks_payment_id
    if payment_id:
        await reconcile_qbo_payment_presentation(
            envelope.connection,
            qbo_payment_id=str(payment_id),
            attempt=envelope.attempt,
            payment=envelope.payment,
            invoice=envelope.invoice,
            qbo_customer_id=customer_id,
            received_principal=receipt_principal,
        )
    else:
        reference = db048_qbo_payment_reference(
            attempt=envelope.attempt,
            payment=envelope.payment,
        )
        matches = await _query(
            envelope.connection,
            f"select * from Payment where PaymentRefNum = '{_escape_query(reference)}' maxresults 1",
        )
        if matches and matches[0].get("Id"):
            candidate = matches[0]
            if (
                str((candidate.get("CustomerRef") or {}).get("value") or "")
                != str(customer_id)
                or money(candidate.get("TotalAmt")) != receipt_principal
                or not _qbo_payment_note_matches(
                    candidate.get("PrivateNote"),
                    attempt=envelope.attempt,
                    payment=envelope.payment,
                    invoice=envelope.invoice,
                )
            ):
                raise DB048ReconciliationError(
                    "QuickBooks payment reference collides with an unrelated receipt"
                )
            payment_id = str(candidate["Id"])
        else:
            response = await _request(
                envelope.connection,
                "POST",
                "payment",
                json=db048_qbo_payment_payload(
                    payment=envelope.payment,
                    invoice=envelope.invoice,
                    qbo_customer_id=customer_id,
                    qbo_invoice_id=qbo_invoice_id,
                    principal_amount=applied_principal,
                    received_principal_amount=receipt_principal,
                    deposit_account=deposit_account,
                    attempt=envelope.attempt,
                    tenant_name=envelope.tenant.name,
                    customer_name=(
                        envelope.customer.company_name
                        or f"{envelope.customer.first_name} {envelope.customer.last_name}"
                    ).strip(),
                ),
                params={"requestid": _qbo_request_id("payment", envelope.attempt.id)},
            )
            qbo_payment = response.get("Payment") if isinstance(response, dict) else None
            if not isinstance(qbo_payment, dict) or not qbo_payment.get("Id"):
                raise QuickBooksAccountingError("QuickBooks did not return the DB-048 payment")
            payment_id = str(qbo_payment["Id"])
        envelope.payment.quickbooks_payment_id = payment_id
    envelope.payment.quickbooks_reconciled_at = datetime.now(timezone.utc)
    envelope.payment.quickbooks_sync_error = None

    # The same QBO Payment owns both the linked principal and any unapplied
    # principal receipt. Credit applications update that one provider object.
    if receipt_principal > applied_principal:
        envelope.link.provider_deposit_id = payment_id

    await _sync_db048_adjustment_journals(envelope)
    await _sync_db048_unearned_surcharge(
        envelope,
        qbo_customer_id=customer_id,
    )
    return str(payment_id)


async def sync_db048_credit_application(
    db: AsyncSession,
    envelope: CreditAccountingEnvelope,
) -> str:
    """Apply consented credit by reallocating its original unapplied QBO Payment."""
    if envelope.config.writer_strategy == "intuit_native":
        envelope.link.sync_state = "awaiting_native_import"
        raise DB048ReconciliationError(
            "Intuit-native credit accounting must be imported, not created by DieselBridge",
            retryable=True,
        )
    source_settlement_id = getattr(envelope.source_attempt, "settlement_id", None)
    if source_settlement_id:
        source_settlement = await db.scalar(select(InvoiceSettlement).where(
            InvoiceSettlement.id == source_settlement_id,
            InvoiceSettlement.tenant_id == envelope.tenant.id,
        ))
        if source_settlement and source_settlement.accounting_composition_version == "gross_invoice_v1":
            from app.services.db048_gross_credit_accounting import sync_gross_credit_application
            return await sync_gross_credit_application(db, envelope, source_settlement)
    source_qbo_payment_id = envelope.source_accounting_link.provider_deposit_id
    if not source_qbo_payment_id:
        raise DB048ReconciliationError(
            "Original unapplied QuickBooks payment is not synchronized yet", retryable=True,
        )
    current = await _request(
        envelope.connection, "GET", f"payment/{source_qbo_payment_id}",
    )
    source_qbo_payment = current.get("Payment") if isinstance(current, dict) else None
    if not isinstance(source_qbo_payment, dict) or str(source_qbo_payment.get("Id")) != str(source_qbo_payment_id):
        raise DB048ReconciliationError(
            "Original unapplied QuickBooks payment is unavailable", retryable=True,
        )
    expected_references = {
        envelope.source_payment.payment_number[:21],
        db048_qbo_payment_reference(
            attempt=envelope.source_attempt,
            payment=envelope.source_payment,
        ),
    }
    if (
        str(source_qbo_payment.get("PaymentRefNum") or "") not in expected_references
        or money(source_qbo_payment.get("TotalAmt"))
        != money(
            envelope.source_attempt.received_amount
            or envelope.source_attempt.principal_amount
        )
        or not _qbo_payment_note_matches(
            source_qbo_payment.get("PrivateNote"),
            attempt=envelope.source_attempt,
            payment=envelope.source_payment,
            invoice=None,
            payment_id=str(source_qbo_payment_id),
        )
    ):
        raise DB048ReconciliationError(
            "QuickBooks credit source collides with an unrelated payment"
        )

    applied_entries = (await db.execute(select(CustomerCreditEntry).where(
        CustomerCreditEntry.tenant_id == envelope.tenant.id,
        CustomerCreditEntry.customer_id == envelope.origin.customer_id,
        CustomerCreditEntry.entry_type == "applied",
        CustomerCreditEntry.source_entry_id == envelope.origin.id,
    ).order_by(CustomerCreditEntry.occurred_at, CustomerCreditEntry.id))).scalars().all()
    if not applied_entries:
        raise DB048ReconciliationError("Customer credit application was not found")
    if money(sum((money(entry.amount) for entry in applied_entries), ZERO)) > money(envelope.origin.amount):
        raise DB048ReconciliationError("Customer credit applications exceed their source payment")

    by_qbo_invoice: dict[str, Decimal] = {}
    for entry in applied_entries:
        reversal_entries = (await db.execute(select(CustomerCreditEntry).where(
            CustomerCreditEntry.tenant_id == envelope.tenant.id,
            CustomerCreditEntry.customer_id == envelope.origin.customer_id,
            CustomerCreditEntry.entry_type == "reversed",
            CustomerCreditEntry.source_entry_id == entry.id,
        ))).scalars().all()
        reversed_amount = money(sum(
            (money(reversal.amount) for reversal in reversal_entries), ZERO
        ))
        recovered_amount = ZERO
        if reversal_entries:
            recovered_amount = money(await db.scalar(select(
                func.coalesce(func.sum(CustomerCreditEntry.amount), 0)
            ).where(
                CustomerCreditEntry.tenant_id == envelope.tenant.id,
                CustomerCreditEntry.customer_id == envelope.origin.customer_id,
                CustomerCreditEntry.entry_type == "applied",
                CustomerCreditEntry.source_entry_id.in_(
                    [reversal.id for reversal in reversal_entries]
                ),
            )))
        active_amount = max(
            ZERO,
            money(entry.amount) - reversed_amount + recovered_amount,
        )
        if active_amount == ZERO:
            continue
        target_invoice = await db.scalar(select(Invoice).where(
            Invoice.id == entry.target_invoice_id,
            Invoice.tenant_id == envelope.tenant.id,
        ))
        target_order = await db.scalar(select(RepairOrder).where(
            RepairOrder.id == (target_invoice.repair_order_id if target_invoice else None),
            RepairOrder.tenant_id == envelope.tenant.id,
            RepairOrder.customer_id == envelope.origin.customer_id,
        ))
        target_customer = await db.scalar(select(Customer).where(
            Customer.id == (target_order.customer_id if target_order else None),
            Customer.tenant_id == envelope.tenant.id,
        ))
        target_settlement = await db.scalar(select(InvoiceSettlement).where(
            InvoiceSettlement.invoice_id == (target_invoice.id if target_invoice else None),
            InvoiceSettlement.tenant_id == envelope.tenant.id,
            InvoiceSettlement.customer_id == envelope.origin.customer_id,
        ))
        if not target_invoice or not target_order or not target_customer or not target_settlement:
            raise DB048ReconciliationError("Customer credit target invoice does not match")
        qbo_customer_id, qbo_invoice_id = await _ensure_db048_qbo_invoice(
            connection=envelope.connection,
            invoice=target_invoice,
            customer=target_customer,
            principal_total=target_settlement.principal_total,
            tenant_name=envelope.tenant.name,
        )
        source_customer_ref = source_qbo_payment.get("CustomerRef") or {}
        if str(source_customer_ref.get("value")) != str(qbo_customer_id):
            raise DB048ReconciliationError("Customer credit QuickBooks customer does not match")
        by_qbo_invoice[qbo_invoice_id] = money(
            by_qbo_invoice.get(qbo_invoice_id, ZERO) + active_amount
        )

    payload = db048_qbo_credit_application_payload(
        source_payment=source_qbo_payment,
        applications=list(by_qbo_invoice.items()),
    )
    response = await _request(
        envelope.connection,
        "POST",
        "payment?operation=update",
        json=payload,
        params={"requestid": _qbo_request_id("credit", envelope.origin.id)},
    )
    updated = response.get("Payment") if isinstance(response, dict) else None
    if not isinstance(updated, dict) or str(updated.get("Id")) != str(source_qbo_payment_id):
        raise QuickBooksAccountingError("QuickBooks did not confirm the customer credit application")
    return str(source_qbo_payment_id)


async def deliver_credit_accounting_envelope(
    db: AsyncSession,
    envelope: CreditAccountingEnvelope,
) -> str:
    from app.services.invoice_accounting_policy import require_exportable_invoice
    await require_exportable_invoice(envelope.target_invoice)
    source_invoice = await db.scalar(select(Invoice).where(
        Invoice.id == envelope.source_attempt.invoice_id,
        Invoice.tenant_id == envelope.tenant.id,
    ))
    if source_invoice is None:
        raise DB048ReconciliationError("Credit source invoice is unavailable")
    await require_exportable_invoice(source_invoice)
    provider_id = await sync_db048_credit_application(db, envelope)
    envelope.link.sync_state = "synced"
    envelope.link.provider_object_id = provider_id
    envelope.link.sync_error = None
    envelope.link.synced_at = datetime.now(timezone.utc)
    remaining = await db.scalar(select(PaymentAccountingLink.id).where(
        PaymentAccountingLink.invoice_id == envelope.target_invoice.id,
        PaymentAccountingLink.tenant_id == envelope.tenant.id,
        PaymentAccountingLink.id != envelope.link.id,
        PaymentAccountingLink.sync_state != "synced",
    ).limit(1))
    envelope.target_settlement.accounting_sync_status = (
        "synced" if remaining is None else "accounting_sync_pending"
    )
    return provider_id


async def sync_db048_refund(envelope: AccountingEnvelope) -> str:
    """Reverse unapplied customer money without touching sales income."""
    if envelope.refund is None:
        raise DB048ReconciliationError("Refund accounting source is missing")
    mappings = envelope.link.account_mapping_snapshot or {}
    if envelope.attempt.provider == "stripe_connect":
        source_account = mappings.get("stripe_clearing_account")
    elif envelope.attempt.provider == "quickbooks_payments":
        source_account = mappings.get("qbp_clearing_account")
    elif envelope.attempt.rail == "check":
        source_account = mappings.get("check_deposit_account")
    else:
        source_account = mappings.get("zelle_ach_account")
    if not source_account:
        raise DB048ReconciliationError("Refund source account mapping is missing")
    receivable_rows = await _query(
        envelope.connection,
        "select * from Account where AccountType = 'Accounts Receivable' maxresults 1",
    )
    if not receivable_rows or not receivable_rows[0].get("Id"):
        raise DB048ReconciliationError("QuickBooks Accounts Receivable account is unavailable", retryable=True)
    customer_id = await ensure_customer(envelope.connection, envelope.customer)
    document_number = f"R-{str(envelope.refund.id).replace('-', '')[:18]}"[:21]
    existing = await _qbo_find_by_doc_number(
        envelope.connection, "JournalEntry", document_number,
    )
    if existing and existing.get("Id"):
        marker = f"DB-048 refund={envelope.refund.id}; unapplied customer overpayment"
        if marker not in str(existing.get("PrivateNote") or ""):
            raise DB048ReconciliationError(
                "QuickBooks refund journal number collides with an unrelated record"
            )
        return str(existing["Id"])
    payload = db048_qbo_overpayment_refund_payload(
        refund=envelope.refund,
        qbo_customer_id=customer_id,
        receivable_account=str(receivable_rows[0]["Id"]),
        source_account=source_account,
    )
    payload["PrivateNote"] = (
        f"DB-048 refund={envelope.refund.id}; unapplied customer overpayment"
    )
    response = await _request(
        envelope.connection,
        "POST",
        "journalentry",
        json=payload,
        params={"requestid": _qbo_request_id("refund", envelope.refund.id)},
    )
    journal = response.get("JournalEntry") if isinstance(response, dict) else None
    if not isinstance(journal, dict) or not journal.get("Id"):
        raise QuickBooksAccountingError("QuickBooks did not return the DB-048 refund reversal")
    return str(journal["Id"])


def _payment_lines_with_delta(
    source_payment: dict[str, Any],
    *,
    source_invoice_id: str,
    source_principal_delta: Decimal,
    allocation_deltas: Optional[dict[str, Decimal]] = None,
) -> list[dict[str, Any]]:
    """Rebuild QBO allocation lines after a signed dispute/recovery."""
    deltas = {
        str(invoice_id): money(delta)
        for invoice_id, delta in (allocation_deltas or {}).items()
        if money(delta) != ZERO
    }
    deltas[str(source_invoice_id)] = money(
        deltas.get(str(source_invoice_id), ZERO) + money(source_principal_delta)
    )
    rebuilt: list[dict[str, Any]] = []
    rows = list(source_payment.get("Line") or [])
    rows.sort(key=lambda row: str(((row.get("LinkedTxn") or [{}])[0]).get("TxnId") or ""))
    for row in rows:
        linked = row.get("LinkedTxn") or []
        if not linked:
            continue
        txn_id = str(linked[0].get("TxnId") or "")
        amount = money(row.get("Amount"))
        if txn_id in deltas:
            amount = money(amount + deltas.pop(txn_id))
            if amount < ZERO:
                raise DB048ReconciliationError(
                    "QuickBooks customer-credit allocation is smaller than its exact dispute reversal"
                )
        if amount > ZERO:
            rebuilt.append({
                "Amount": float(amount),
                "LinkedTxn": linked,
            })
    for invoice_id in sorted(deltas):
        delta = money(deltas[invoice_id])
        if delta < ZERO:
            raise DB048ReconciliationError(
                "QuickBooks customer-credit target is missing from the disputed receipt"
            )
        if delta > ZERO:
            rebuilt.append({
                "Amount": float(delta),
                "LinkedTxn": [{"TxnId": invoice_id, "TxnType": "Invoice"}],
            })
    rebuilt.sort(
        key=lambda row: str(
            ((row.get("LinkedTxn") or [{}])[0]).get("TxnId") or ""
        )
    )
    return rebuilt


async def _dispute_credit_qbo_deltas(
    db: AsyncSession,
    envelope: AccountingEnvelope,
    *,
    recovery: bool,
    qbo_customer_id: str,
) -> dict[str, Decimal]:
    """Resolve immutable local credit reversal/recovery rows to exact QBO A/R."""
    dispute = envelope.dispute
    if not dispute:
        return {}
    reversals = (await db.execute(select(CustomerCreditEntry).where(
        CustomerCreditEntry.tenant_id == envelope.tenant.id,
        CustomerCreditEntry.customer_id == envelope.attempt.customer_id,
        CustomerCreditEntry.entry_type == "reversed",
        CustomerCreditEntry.target_invoice_id.is_not(None),
        CustomerCreditEntry.idempotency_key.like(
            f"dispute:{dispute.id}:credit:%"
        ),
    ).order_by(CustomerCreditEntry.id))).scalars().all()
    deltas: dict[str, Decimal] = {}
    for reversal in reversals:
        if not recovery:
            source_application_link = await db.scalar(select(
                PaymentAccountingLink
            ).where(
                PaymentAccountingLink.tenant_id == envelope.tenant.id,
                PaymentAccountingLink.financial_object_type
                == "customer_credit_application",
                PaymentAccountingLink.financial_object_id
                == reversal.source_entry_id,
            ))
            # If the application never reached QBO there is no provider line
            # to remove. The local target still reopens and a later won event
            # can add the exact restored line from its compensation entry.
            if (
                not source_application_link
                or source_application_link.sync_state != "synced"
            ):
                continue
        if recovery:
            recovered = money(await db.scalar(select(
                func.coalesce(func.sum(CustomerCreditEntry.amount), 0)
            ).where(
                CustomerCreditEntry.tenant_id == envelope.tenant.id,
                CustomerCreditEntry.customer_id == envelope.attempt.customer_id,
                CustomerCreditEntry.entry_type == "applied",
                CustomerCreditEntry.source_entry_id == reversal.id,
            )))
            delta = recovered
        else:
            delta = -money(reversal.amount)
        if delta == ZERO:
            continue
        target_invoice = await db.scalar(select(Invoice).where(
            Invoice.id == reversal.target_invoice_id,
            Invoice.tenant_id == envelope.tenant.id,
        ))
        target_order = await db.scalar(select(RepairOrder).where(
            RepairOrder.id == (
                target_invoice.repair_order_id if target_invoice else None
            ),
            RepairOrder.tenant_id == envelope.tenant.id,
            RepairOrder.customer_id == envelope.attempt.customer_id,
        ))
        target_customer = await db.scalar(select(Customer).where(
            Customer.id == (
                target_order.customer_id if target_order else None
            ),
            Customer.tenant_id == envelope.tenant.id,
        ))
        target_settlement = await db.scalar(select(InvoiceSettlement).where(
            InvoiceSettlement.invoice_id == (
                target_invoice.id if target_invoice else None
            ),
            InvoiceSettlement.tenant_id == envelope.tenant.id,
            InvoiceSettlement.customer_id == envelope.attempt.customer_id,
        ))
        if (
            not target_invoice
            or not target_order
            or not target_customer
            or not target_settlement
        ):
            raise DB048ReconciliationError(
                "Dispute QuickBooks customer-credit target is unavailable"
            )
        target_customer_id, target_qbo_invoice_id = await _ensure_db048_qbo_invoice(
            connection=envelope.connection,
            invoice=target_invoice,
            customer=target_customer,
            principal_total=target_settlement.principal_total,
            tenant_name=envelope.tenant.name,
        )
        if str(target_customer_id) != str(qbo_customer_id):
            raise DB048ReconciliationError(
                "Dispute QuickBooks customer-credit owner does not match"
            )
        deltas[target_qbo_invoice_id] = money(
            deltas.get(target_qbo_invoice_id, ZERO) + delta
        )
    return deltas


def _qbo_payment_update_payload(
    source_payment: dict[str, Any],
    *,
    total_amount: Decimal,
    lines: list[dict[str, Any]],
    note: str,
) -> dict[str, Any]:
    payment_id = source_payment.get("Id")
    sync_token = source_payment.get("SyncToken")
    customer_ref = source_payment.get("CustomerRef")
    if not payment_id or sync_token is None or not customer_ref:
        raise DB048ReconciliationError("QuickBooks payment identity is incomplete")
    payload: dict[str, Any] = {
        "Id": str(payment_id),
        "SyncToken": str(sync_token),
        "CustomerRef": customer_ref,
        "TotalAmt": float(money(total_amount)),
        "Line": lines,
        "PrivateNote": note,
    }
    for key in (
        "PaymentRefNum", "DepositToAccountRef", "TxnDate", "PaymentMethodRef",
        "CurrencyRef", "ExchangeRate",
    ):
        if source_payment.get(key) is not None:
            payload[key] = source_payment[key]
    return payload


async def _sync_dispute_fee_journal(
    envelope: AccountingEnvelope,
    *,
    recovery: bool,
) -> Optional[str]:
    dispute = envelope.dispute
    if not dispute:
        raise DB048ReconciliationError("Dispute accounting source is missing")
    mappings = envelope.link.account_mapping_snapshot or {}
    clearing = mappings.get("stripe_clearing_account")
    fee_income = mappings.get("card_fee_income_account")
    tax_liability = mappings.get("sales_tax_liability_account")
    disputed_fee = money(dispute.reversed_card_fee_amount)
    disputed_fee_tax = money(dispute.reversed_card_fee_tax_amount)
    original_unearned = money(dispute.reversed_unearned_surcharge_amount)
    if recovery:
        reversed_principal = money(dispute.reversed_principal_amount)
        restored_principal = money(envelope.link.principal_amount_snapshot)
        if reversed_principal > ZERO:
            fee = money(disputed_fee * restored_principal / reversed_principal)
            fee_tax = money(disputed_fee_tax * restored_principal / reversed_principal)
        else:
            fee = fee_tax = ZERO
        customer_unapplied = money(
            original_unearned
            + disputed_fee - fee
            + disputed_fee_tax - fee_tax
        )
    else:
        fee = disputed_fee
        fee_tax = disputed_fee_tax
        customer_unapplied = original_unearned
    total = money(fee + fee_tax + customer_unapplied)
    if total == ZERO:
        return None
    if not clearing or (fee > ZERO and not fee_income) or (fee_tax > ZERO and not tax_liability):
        raise DB048ReconciliationError("Dispute fee accounting mappings are incomplete")
    receivable_account = customer_id = None
    if customer_unapplied > ZERO:
        receivable_rows = await _query(
            envelope.connection,
            "select * from Account where AccountType = 'Accounts Receivable' maxresults 1",
        )
        if not receivable_rows or not receivable_rows[0].get("Id"):
            raise DB048ReconciliationError(
                "QuickBooks Accounts Receivable account is unavailable", retryable=True,
            )
        receivable_account = str(receivable_rows[0]["Id"])
        customer_id = await ensure_customer(envelope.connection, envelope.customer)
    prefix = "DW" if recovery else "D"
    document_number = f"{prefix}-{str(dispute.id).replace('-', '')[:18]}"[:21]
    existing = await _qbo_find_by_doc_number(
        envelope.connection, "JournalEntry", document_number,
    )
    if existing and existing.get("Id"):
        return str(existing["Id"])
    lines: list[dict[str, Any]] = []
    # Created dispute reverses fee income/tax and credits clearing. A won
    # dispute restores those exact entries. Any now-unearned recovery is
    # handled as refundable unapplied money by the local recovery projection.
    clearing_posting = "Debit" if recovery else "Credit"
    component_posting = "Credit" if recovery else "Debit"
    lines.append({
        "Amount": float(total),
        "DetailType": "JournalEntryLineDetail",
        "JournalEntryLineDetail": {
            "PostingType": clearing_posting,
            "AccountRef": {"value": clearing},
        },
    })
    if fee > ZERO:
        lines.append({
            "Amount": float(fee),
            "DetailType": "JournalEntryLineDetail",
            "JournalEntryLineDetail": {
                "PostingType": component_posting,
                "AccountRef": {"value": fee_income},
            },
        })
    if fee_tax > ZERO:
        lines.append({
            "Amount": float(fee_tax),
            "DetailType": "JournalEntryLineDetail",
            "JournalEntryLineDetail": {
                "PostingType": component_posting,
                "AccountRef": {"value": tax_liability},
            },
        })
    if customer_unapplied > ZERO:
        lines.append({
            "Amount": float(customer_unapplied),
            "DetailType": "JournalEntryLineDetail",
            "JournalEntryLineDetail": {
                "PostingType": component_posting,
                "AccountRef": {"value": receivable_account},
                "Entity": {
                    "Type": "Customer",
                    "EntityRef": {"value": customer_id},
                },
            },
        })
    response = await _request(
        envelope.connection,
        "POST",
        "journalentry",
        json={
            "DocNumber": document_number,
            "PrivateNote": (
                "DB-048 signed Stripe dispute won recovery"
                if recovery else "DB-048 signed Stripe dispute reversal"
            ),
            "Line": lines,
        },
        params={"requestid": _qbo_request_id("dispute", f"{dispute.id}:{recovery}")},
    )
    journal = response.get("JournalEntry") if isinstance(response, dict) else None
    if not isinstance(journal, dict) or not journal.get("Id"):
        raise QuickBooksAccountingError("QuickBooks did not return the dispute adjustment")
    return str(journal["Id"])


async def sync_db048_dispute(
    db: AsyncSession,
    envelope: AccountingEnvelope,
    *,
    recovery: bool,
) -> str:
    dispute = envelope.dispute
    if not dispute:
        raise DB048ReconciliationError("Dispute accounting source is missing")
    payment_id = envelope.payment.quickbooks_payment_id
    if not payment_id:
        raise DB048ReconciliationError(
            "Original QuickBooks payment is not synchronized yet", retryable=True,
        )
    current = await _request(envelope.connection, "GET", f"payment/{payment_id}")
    qbo_payment = current.get("Payment") if isinstance(current, dict) else None
    if not isinstance(qbo_payment, dict) or str(qbo_payment.get("Id")) != str(payment_id):
        raise DB048ReconciliationError("Original QuickBooks payment is unavailable", retryable=True)
    customer_id, qbo_invoice_id = await _ensure_db048_qbo_invoice(
        connection=envelope.connection,
        invoice=envelope.invoice,
        customer=envelope.customer,
        principal_total=envelope.settlement.principal_total,
        tenant_name=envelope.tenant.name,
    )
    if str((qbo_payment.get("CustomerRef") or {}).get("value") or "") != str(customer_id):
        raise DB048ReconciliationError("Dispute QuickBooks customer does not match")
    credit_deltas = await _dispute_credit_qbo_deltas(
        db,
        envelope,
        recovery=recovery,
        qbo_customer_id=customer_id,
    )
    principal = money(envelope.link.principal_amount_snapshot)
    principal_receipt_component = money(
        dispute.reversed_principal_amount
        + dispute.reversed_unapplied_principal_amount
    )
    current_total = money(qbo_payment.get("TotalAmt"))
    if recovery:
        new_total = money(current_total + principal_receipt_component)
        lines = _payment_lines_with_delta(
            qbo_payment,
            source_invoice_id=qbo_invoice_id,
            source_principal_delta=principal,
            allocation_deltas=credit_deltas,
        )
    else:
        if principal_receipt_component > current_total:
            raise DB048ReconciliationError("Dispute exceeds the QuickBooks receipt")
        new_total = money(current_total - principal_receipt_component)
        lines = _payment_lines_with_delta(
            qbo_payment,
            source_invoice_id=qbo_invoice_id,
            source_principal_delta=-money(dispute.reversed_principal_amount),
            allocation_deltas=credit_deltas,
        )
    response = await _request(
        envelope.connection,
        "POST",
        "payment?operation=update",
        json=_qbo_payment_update_payload(
            qbo_payment,
            total_amount=new_total,
            lines=lines,
            note=(
                f"DB-048 dispute={dispute.provider_dispute_id} won recovery"
                if recovery else f"DB-048 dispute={dispute.provider_dispute_id} reversal"
            ),
        ),
        params={
            "requestid": _qbo_request_id(
                "dispute", f"{dispute.id}:{'won' if recovery else 'created'}",
            )
        },
    )
    updated = response.get("Payment") if isinstance(response, dict) else None
    if not isinstance(updated, dict) or str(updated.get("Id")) != str(payment_id):
        raise QuickBooksAccountingError("QuickBooks did not confirm the dispute payment update")
    await _sync_dispute_fee_journal(envelope, recovery=recovery)
    return str(payment_id)


async def sync_db048_reversal(envelope: AccountingEnvelope) -> str:
    """Void every QBO Payment funded by the reversed provider receipt.

    The principal Payment reopens the source invoice.  When an accidental
    overpayment was consented to credit and subsequently applied, the separate
    unapplied Payment carries those target-invoice links; voiding it reopens
    those invoices without manufacturing a Credit Memo or a second receipt.
    """
    payment_id = envelope.payment.quickbooks_payment_id
    if not payment_id:
        raise DB048ReconciliationError(
            "Original QuickBooks payment is not synchronized yet", retryable=True,
        )
    payment_ids = [str(payment_id)]
    unapplied_payment_id = getattr(
        getattr(envelope, "link", None), "provider_deposit_id", None,
    )
    if unapplied_payment_id and str(unapplied_payment_id) not in payment_ids:
        payment_ids.append(str(unapplied_payment_id))
    expected_customer_id = await ensure_customer(
        envelope.connection,
        envelope.customer,
        tenant_name=envelope.tenant.name,
    )
    expected_total = money(
        envelope.attempt.received_amount
        if envelope.attempt.received_amount is not None
        else envelope.attempt.principal_amount
    )
    for qbo_payment_id in payment_ids:
        current = await _request(
            envelope.connection, "GET", f"payment/{qbo_payment_id}",
        )
        payment = current.get("Payment") if isinstance(current, dict) else None
        if not isinstance(payment, dict) or str(payment.get("Id")) != qbo_payment_id:
            raise DB048ReconciliationError(
                "Original QuickBooks payment is unavailable", retryable=True,
            )
        reference = str(payment.get("PaymentRefNum") or "")
        legacy_reference = envelope.payment.payment_number[:21]
        expected_reference = db048_qbo_payment_reference(
            attempt=envelope.attempt,
            payment=envelope.payment,
        )
        if (
            str((payment.get("CustomerRef") or {}).get("value") or "")
            != str(expected_customer_id)
            or (
                str(payment.get("TxnStatus", "")).casefold() != "voided"
                and money(payment.get("TotalAmt")) != expected_total
            )
            or
            reference not in {
                expected_reference,
                legacy_reference,
                f"U-{legacy_reference}"[:21],
            }
            or not _qbo_payment_note_matches(
                payment.get("PrivateNote"),
                attempt=envelope.attempt,
                payment=envelope.payment,
                invoice=getattr(envelope, "invoice", None),
                payment_id=qbo_payment_id,
            )
        ):
            raise DB048ReconciliationError(
                "QuickBooks reversal target collides with an unrelated payment"
            )
        if (
            str(payment.get("TxnStatus", "")).casefold() != "voided"
            and money(payment.get("TotalAmt")) > ZERO
        ):
            response = await _request(
                envelope.connection,
                "POST",
                "payment?operation=void",
                json={
                    "Id": str(payment["Id"]),
                    "SyncToken": str(payment.get("SyncToken", "0")),
                },
                params={
                    "requestid": _qbo_request_id(
                        "reversal", f"{envelope.link.financial_object_id}:{qbo_payment_id}",
                    )
                },
            )
            voided = response.get("Payment") if isinstance(response, dict) else None
            if not isinstance(voided, dict) or str(voided.get("Id")) != qbo_payment_id:
                raise QuickBooksAccountingError(
                    "QuickBooks did not confirm the payment reversal",
                )
    return str(payment_id)


async def deliver_accounting_envelope(
    db: AsyncSession,
    envelope: AccountingEnvelope,
    *,
    sync_payment_func: Optional[Callable[[AccountingEnvelope], Awaitable[str]]] = None,
    sync_refund_func: Optional[Callable[[AccountingEnvelope], Awaitable[str]]] = None,
) -> str:
    if envelope.config.writer_strategy == "intuit_native":
        envelope.link.sync_state = "awaiting_native_import"
        raise DB048ReconciliationError(
            "Intuit-native accounting must be imported, not created by DieselBridge",
            retryable=True,
        )
    from app.services.invoice_accounting_policy import require_exportable_invoice
    await require_exportable_invoice(envelope.invoice)
    from app.services.db048_qbo_gross_accounting import is_gross, deliver_gross_envelope
    if is_gross(envelope.settlement):
        provider_id = await deliver_gross_envelope(db, envelope)
    elif envelope.link.financial_object_type == "payment_dispute":
        provider_id = await sync_db048_dispute(db, envelope, recovery=False)
    elif envelope.link.financial_object_type == "payment_dispute_recovery":
        provider_id = await sync_db048_dispute(db, envelope, recovery=True)
    elif envelope.link.financial_object_type == "payment_reversal":
        provider_id = await sync_db048_reversal(envelope)
    elif envelope.refund:
        provider_id = await (
            sync_refund_func(envelope) if sync_refund_func else sync_db048_refund(envelope)
        )
    else:
        provider_id = await (
            sync_payment_func(envelope) if sync_payment_func else sync_db048_payment(envelope)
        )
    envelope.link.sync_state = "synced"
    envelope.link.provider_object_id = provider_id
    envelope.link.sync_error = None
    envelope.link.synced_at = datetime.now(timezone.utc)
    settlement = (await db.execute(select(InvoiceSettlement).where(
        InvoiceSettlement.invoice_id == envelope.invoice.id,
        InvoiceSettlement.tenant_id == envelope.tenant.id,
    ))).scalar_one()
    remaining = (await db.execute(select(PaymentAccountingLink).where(
        PaymentAccountingLink.invoice_id == envelope.invoice.id,
        PaymentAccountingLink.tenant_id == envelope.tenant.id,
        PaymentAccountingLink.id != envelope.link.id,
        PaymentAccountingLink.sync_state != "synced",
    ))).scalars().first()
    settlement.accounting_sync_status = "synced" if remaining is None else "accounting_sync_pending"
    if envelope.link.financial_object_type == "payment_reversal":
        # A reversed provider receipt may have funded customer-credit
        # applications on other invoices. The QBO unapplied Payment void above
        # reopens those invoices; mirror that finality on their projections.
        overpayment = await db.scalar(select(PaymentOverpayment).where(
            PaymentOverpayment.tenant_id == envelope.tenant.id,
            PaymentOverpayment.source_attempt_id == envelope.attempt.id,
        ))
        origins = (await db.execute(select(CustomerCreditEntry.id).where(
            CustomerCreditEntry.tenant_id == envelope.tenant.id,
            CustomerCreditEntry.origin_overpayment_id == (
                overpayment.id if overpayment else None
            ),
            CustomerCreditEntry.entry_type == "issued",
        ))).scalars().all()
        if origins:
            target_invoice_ids = set((await db.execute(
                select(CustomerCreditEntry.target_invoice_id).where(
                    CustomerCreditEntry.tenant_id == envelope.tenant.id,
                    CustomerCreditEntry.source_entry_id.in_(origins),
                    CustomerCreditEntry.entry_type == "applied",
                    CustomerCreditEntry.target_invoice_id.is_not(None),
                )
            )).scalars().all())
            for target_invoice_id in target_invoice_ids:
                target_settlement = await db.scalar(select(InvoiceSettlement).where(
                    InvoiceSettlement.tenant_id == envelope.tenant.id,
                    InvoiceSettlement.invoice_id == target_invoice_id,
                ).with_for_update())
                if not target_settlement:
                    continue
                actionable_link = await db.scalar(select(PaymentAccountingLink.id).where(
                    PaymentAccountingLink.tenant_id == envelope.tenant.id,
                    PaymentAccountingLink.invoice_id == target_invoice_id,
                    PaymentAccountingLink.sync_state.in_([
                        "pending", "processing", "failed", "dead",
                        "awaiting_native_import",
                    ]),
                ).limit(1))
                target_settlement.accounting_sync_status = (
                    "synced" if actionable_link is None else "accounting_sync_pending"
                )
    return provider_id


async def _submit_stripe_refund(db: AsyncSession, event: ProviderOutboxEvent) -> str:
    """Submit the snapshotted attempt to its original card provider.

    The historical function name is retained for test/import compatibility,
    but DB-048 supports both approved card providers here.  A provider switch
    never moves an existing refund to the tenant's new provider.
    """
    payload = event.payload or {}
    try:
        refund_id = UUID(str(payload["refund_id"]))
        attempt_id = UUID(str(payload["attempt_id"]))
    except (KeyError, TypeError, ValueError) as exc:
        raise DB048ReconciliationError("Refund outbox envelope is invalid") from exc
    refund = (await db.execute(select(PaymentRefund).where(
        PaymentRefund.id == refund_id,
        PaymentRefund.tenant_id == event.tenant_id,
        PaymentRefund.source_attempt_id == attempt_id,
    ).with_for_update())).scalar_one_or_none()
    attempt = (await db.execute(select(InvoicePaymentAttempt).where(
        InvoicePaymentAttempt.id == attempt_id,
        InvoicePaymentAttempt.tenant_id == event.tenant_id,
    ))).scalar_one_or_none()
    if (
        not refund
        or not attempt
        or refund.mode != "automatic"
        or not attempt.provider_charge_id
        or attempt.provider not in {"stripe_connect", "quickbooks_payments"}
    ):
        raise DB048ReconciliationError("Refund source does not match a reversible card charge")
    if refund.state == "succeeded":
        return refund.provider_reference or str(refund.id)
    if refund.state == "cancelled":
        return str(refund.id)
    from app.services.invoice_accounting_policy import require_standard_payment
    source_invoice = await db.scalar(select(Invoice).where(
        Invoice.id == attempt.invoice_id, Invoice.tenant_id == event.tenant_id))
    if source_invoice is None:
        raise DB048ReconciliationError("Refund invoice is unavailable")
    await require_standard_payment(db, source_invoice)
    if attempt.provider == "quickbooks_payments":
        if refund.state != "pending":
            raise DB048ReconciliationError("QuickBooks refund requires explicit state reconciliation")
        config = await db.scalar(select(TenantPaymentProviderConfiguration).where(
            TenantPaymentProviderConfiguration.tenant_id == event.tenant_id,
            TenantPaymentProviderConfiguration.version == attempt.provider_configuration_version,
            TenantPaymentProviderConfiguration.selected_provider == "quickbooks_payments",
            TenantPaymentProviderConfiguration.writer_strategy == "dieselbridge",
        ))
        connection = await db.scalar(select(QuickBooksConnection).where(
            QuickBooksConnection.tenant_id == event.tenant_id,
            QuickBooksConnection.status == "connected",
            QuickBooksConnection.deleted_at.is_(None),
        ))
        if (not config or not connection or connection.realm_id != config.qbo_realm_snapshot
                or attempt.provider_account_id != config.provider_account_snapshot
                or refund.invoice_id != attempt.invoice_id):
            raise DB048ReconciliationError(
                "QuickBooks refund connection does not match the original provider configuration",
                retryable=True,
            )
        # An accepted ID is reconciled by GET, never another monetary POST.
        # A lost first response cannot safely be retried: the sandbox rejects
        # same-key refund replay with 400 rather than returning the first ID.
        if not refund.provider_reference and (
            refund.last_error == "qbp_refund_outcome_unknown" or (event.attempt_count or 0) > 1
        ):
            refund.last_error = "qbp_refund_outcome_unknown"
            return str(refund.id)
        known_refund = bool(refund.provider_reference)
        try:
            if known_refund:
                response = await get_quickbooks_refund(
                    connection=connection, charge_id=attempt.provider_charge_id,
                    refund_id=refund.provider_reference,
                )
            else:
                response = await refund_quickbooks_charge(
                    connection=connection,
                    charge_id=attempt.provider_charge_id,
                    amount=money(refund.amount),
                    description=refund.reason,
                    request_id=f"db048-refund-{refund.id}"[:255],
                )
        except QuickBooksPaymentError:
            # A rejection to THIS request does not prove the original refund
            # failed. Keep money pending for GET/owner reconciliation.
            refund.last_error = "qbp_refund_outcome_unknown"
            return refund.provider_reference or str(refund.id)
        if refund.provider_reference and response.id != refund.provider_reference:
            refund.last_error = "qbp_refund_identity_mismatch"
            return refund.provider_reference
        refund.provider_reference = response.id
        if money(response.amount) != money(refund.amount):
            refund.last_error = "qbp_refund_amount_mismatch"
            return refund.provider_reference
        provider_reference = response.id
        normalized_status = response.status.casefold()
        if normalized_status == "declined" and known_refund:
            await finalize_provider_refund(
                db, refund_id=refund.id, tenant_id=event.tenant_id,
                provider_account_id=attempt.provider_account_id,
                provider_reference=provider_reference,
                provider_event_id=f"refund-submit:{provider_reference}:declined",
                provider_status="failed",
            )
            return provider_reference
        if normalized_status not in {"succeeded", "completed", "captured", "refunded", "settled"}:
            # ISSUED is observed provider acceptance, not evidence of bank
            # settlement. Persist the ID without releasing pending money.
            refund.last_error = "qbp_refund_accepted_pending" if normalized_status == "issued" else "qbp_refund_outcome_unknown"
            return provider_reference
        await finalize_provider_refund(
            db,
            refund_id=refund.id,
            tenant_id=event.tenant_id,
            provider_account_id=attempt.provider_account_id,
            provider_reference=provider_reference,
            provider_event_id=f"refund-submit:{provider_reference}:{normalized_status}",
            provider_status="succeeded",
        )
        return provider_reference

    try:
        response = stripe.Refund.create(
            charge=attempt.provider_charge_id,
            amount=int(money(refund.amount) * 100),
            # DB-048 uses Connect direct charges. Stripe does not return the
            # platform application fee unless explicitly requested; use the
            # proportional refund behavior for partial reversals and never
            # request reverse_transfer on a connected-account direct charge.
            refund_application_fee=True,
            stripe_account=attempt.provider_account_id,
            idempotency_key=f"db048-refund:{event.tenant_id}:{refund.id}",
            metadata={
                "tenant_id": str(event.tenant_id),
                "invoice_id": str(refund.invoice_id),
                "payment_refund_id": str(refund.id),
            },
        )
    except stripe.error.StripeError as exc:
        refund.retry_count += 1
        refund.last_error = type(exc).__name__
        raise DB048ReconciliationError("Stripe refund submission failed", retryable=True) from exc
    provider_reference = str(getattr(response, "id", None) or response.get("id"))
    refund.provider_reference = provider_reference
    refund.last_error = None
    provider_status = str(getattr(response, "status", None) or response.get("status") or "pending")
    overpayment = (await db.execute(select(PaymentOverpayment).where(
        PaymentOverpayment.id == refund.overpayment_id,
        PaymentOverpayment.tenant_id == event.tenant_id,
    ).with_for_update())).scalar_one_or_none()
    if provider_status in {"failed", "canceled", "cancelled"}:
        await finalize_provider_refund(
            db,
            refund_id=refund.id,
            tenant_id=event.tenant_id,
            provider_account_id=attempt.provider_account_id,
            provider_reference=provider_reference,
            provider_event_id=f"refund-submit:{provider_reference}:{provider_status}",
            provider_status=provider_status,
        )
    elif overpayment:
        # Refund.create confirms submission, not financial finality.  Even if
        # Stripe's immediate response says `succeeded`, DB-048 waits for the
        # separately signature-verified refund event before reducing refund
        # pending money or emitting accounting.
        overpayment.state = "refunding"
    return provider_reference


async def finalize_provider_refund(
    db: AsyncSession,
    *,
    refund_id: UUID,
    tenant_id: UUID,
    provider_account_id: Optional[str],
    provider_reference: str,
    provider_event_id: str,
    provider_status: str,
) -> PaymentRefund:
    """Apply one signed/provider-verified refund terminal state idempotently."""
    refund = (await db.execute(select(PaymentRefund).where(
        PaymentRefund.id == refund_id,
        PaymentRefund.tenant_id == tenant_id,
    ).with_for_update())).scalar_one_or_none()
    if not refund:
        raise DB048ReconciliationError("Refund was not found")
    attempt = (await db.execute(select(InvoicePaymentAttempt).where(
        InvoicePaymentAttempt.id == refund.source_attempt_id,
        InvoicePaymentAttempt.tenant_id == tenant_id,
    ))).scalar_one_or_none()
    provider_identity_matches = bool(
        attempt
        and attempt.provider in {"stripe_connect", "quickbooks_payments"}
        and (
            attempt.provider != "stripe_connect"
            or attempt.provider_account_id == provider_account_id
        )
    )
    if not provider_identity_matches or (
        refund.provider_reference and refund.provider_reference != provider_reference
    ):
        raise DB048ReconciliationError("Refund provider identity does not match")
    settlement = (await db.execute(select(InvoiceSettlement).where(
        InvoiceSettlement.invoice_id == refund.invoice_id,
        InvoiceSettlement.tenant_id == tenant_id,
    ).with_for_update())).scalar_one()
    event_key = f"refund-provider:{provider_account_id}:{provider_event_id}"
    existing_event = (await db.execute(select(InvoicePaymentLedgerEvent).where(
        # Do not trust reordered or duplicated provider deliveries to repeat a
        # money transition.
        InvoicePaymentLedgerEvent.tenant_id == tenant_id,
        InvoicePaymentLedgerEvent.idempotency_key == event_key,
    ))).scalar_one_or_none()
    if existing_event:
        return refund
    refund.provider_reference = provider_reference
    normalized = provider_status.casefold()
    if normalized != "succeeded":
        if refund.state == "succeeded":
            return refund
        refund.state = "failed"
        refund.last_error = f"provider_refund_{normalized}"[:255]
        overpayment = await db.get(PaymentOverpayment, refund.overpayment_id) if refund.overpayment_id else None
        if overpayment:
            overpayment.state = "refund_required"
        await append_ledger_event(
            db,
            settlement=settlement,
            attempt=attempt,
            event_type="refund_failed",
            idempotency_key=event_key,
            actor=None,
            evidence={"refund_id": str(refund.id), "provider_status": normalized},
        )
        return refund
    if refund.state == "succeeded":
        return refund
    refund.state = "succeeded"
    refund.completed_at = datetime.now(timezone.utc)
    refund.last_error = None
    settlement = (await db.execute(select(InvoiceSettlement).where(
        InvoiceSettlement.invoice_id == refund.invoice_id,
        InvoiceSettlement.tenant_id == tenant_id,
    ).with_for_update())).scalar_one()
    overpayment = await db.get(PaymentOverpayment, refund.overpayment_id) if refund.overpayment_id else None
    if overpayment is None:
        # A successful QBP amount-mismatch charge is never applied to A/R.
        # Its compensating full refund releases the still-pending reservation
        # without inventing unapplied credit or a legacy negative payment.
        prior_state = settlement.state
        if attempt.state == "pending":
            settlement.active_pending_principal = max(
                ZERO,
                money(settlement.active_pending_principal) - money(attempt.principal_amount),
            )
            attempt.state = "failed"
            attempt.failed_at = datetime.now(timezone.utc)
            attempt.failure_code = "provider_payment_mismatch_refunded"
            attempt.version += 1
        settlement.version += 1
        settlement.state = settlement_state(settlement)
        await append_ledger_event(
            db,
            settlement=settlement,
            attempt=attempt,
            event_type="refund_succeeded",
            idempotency_key=event_key,
            actor=None,
            prior_state=prior_state,
            new_state=settlement.state,
            pending_delta=-money(attempt.principal_amount),
            evidence={
                "refund_id": str(refund.id),
                "provider_reference_present": True,
                "resolution": "provider_amount_mismatch_full_refund",
            },
        )
        return refund
    settlement.refund_pending = max(ZERO, money(settlement.refund_pending) - money(refund.amount))
    settlement.unapplied_credit = max(ZERO, money(settlement.unapplied_credit) - money(refund.amount))
    settlement.version += 1
    settlement.state = settlement_state(settlement)
    await append_ledger_event(
        db,
        settlement=settlement,
        attempt=attempt,
        event_type="refund_succeeded",
        idempotency_key=event_key,
        actor=None,
        unapplied_delta=-money(refund.amount),
        refund_pending_delta=-money(refund.amount),
        evidence={"refund_id": str(refund.id), "provider_reference_present": True},
    )
    overpayment.state = "refunded"
    overpayment.resolved_at = datetime.now(timezone.utc)
    config = (await db.execute(select(TenantPaymentProviderConfiguration).where(
        TenantPaymentProviderConfiguration.tenant_id == tenant_id,
        TenantPaymentProviderConfiguration.version == attempt.provider_configuration_version,
    ))).scalar_one()
    link = (await db.execute(select(PaymentAccountingLink).where(
        PaymentAccountingLink.tenant_id == tenant_id,
        PaymentAccountingLink.financial_object_type == "invoice_refund",
        PaymentAccountingLink.financial_object_id == refund.id,
        PaymentAccountingLink.operation_version == 1,
    ))).scalar_one_or_none()
    if link:
        return refund
    link = PaymentAccountingLink(
        tenant_id=tenant_id,
        invoice_id=refund.invoice_id,
        attempt_id=attempt.id,
        refund_id=refund.id,
        financial_object_type="invoice_refund",
        financial_object_id=refund.id,
        operation_version=1,
        owning_writer=config.writer_strategy,
        account_mapping_snapshot={
            key: getattr(config, key)
            for key in (
                "stripe_clearing_account", "qbp_clearing_account",
                "check_deposit_account", "zelle_ach_account",
                "card_fee_income_account", "processor_fee_expense_account",
                "sales_tax_liability_account", "checking_account",
            )
        },
        qbo_realm_snapshot=config.qbo_realm_snapshot,
        sync_state="pending",
    )
    db.add(link)
    await db.flush()
    db.add(ProviderOutboxEvent(
        tenant_id=tenant_id,
        event_type=REFUND_ACCOUNTING_EVENT,
        aggregate_type="payment_refund",
        aggregate_id=refund.id,
        payload={
            "accounting_link_id": str(link.id),
            "attempt_id": str(attempt.id),
            "invoice_id": str(refund.invoice_id),
            "refund_id": str(refund.id),
        },
        idempotency_key=f"invoice-refund:{refund.id}:accounting:v1",
        status=ProviderOutboxStatus.PENDING.value,
        available_at=datetime.now(timezone.utc),
    ))
    return refund


def _configuration_mapping_snapshot(
    config: TenantPaymentProviderConfiguration,
) -> dict[str, Optional[str]]:
    return {
        key: getattr(config, key)
        for key in (
            "stripe_clearing_account", "qbp_clearing_account",
            "check_deposit_account", "zelle_ach_account",
            "card_fee_income_account", "processor_fee_expense_account",
            "sales_tax_liability_account", "checking_account",
        )
    }


def _split_disputed_gross(
    amount: Decimal,
    *,
    principal: Decimal,
    card_fee: Decimal,
    card_fee_tax: Decimal,
    unapplied: Decimal,
) -> tuple[Decimal, Decimal, Decimal, Decimal]:
    """Allocate an exact provider dispute across retained receipt components."""
    amount = money(amount)
    components = [money(principal), money(card_fee), money(card_fee_tax), money(unapplied)]
    available = money(sum(components, ZERO))
    if amount <= ZERO or amount > available:
        raise DB048ReconciliationError("Stripe dispute amount exceeds retained provider money")
    if amount == available:
        return tuple(components)  # type: ignore[return-value]
    shares: list[Decimal] = []
    remaining = amount
    for component in components[:-1]:
        share = min(component, money(amount * component / available))
        shares.append(share)
        remaining = money(remaining - share)
    final = min(components[-1], remaining)
    shares.append(final)
    remaining = money(amount - sum(shares, ZERO))
    if remaining > ZERO:
        # Cent rounding can leave a small remainder. Allocate it in stable
        # economic order without ever exceeding a component's capacity.
        for index, component in enumerate(components):
            capacity = money(component - shares[index])
            if capacity <= ZERO:
                continue
            delta = min(capacity, remaining)
            shares[index] = money(shares[index] + delta)
            remaining = money(remaining - delta)
            if remaining == ZERO:
                break
    if remaining != ZERO or money(sum(shares, ZERO)) != amount:
        raise DB048ReconciliationError("Stripe dispute allocation could not be reconciled")
    return shares[0], shares[1], shares[2], shares[3]


async def _reverse_applied_credit_for_dispute(
    db: AsyncSession,
    *,
    attempt: InvoicePaymentAttempt,
    dispute: PaymentProviderDispute,
    amount: Decimal,
) -> None:
    """Reopen invoices funded by disputed customer credit, newest first.

    Application-reversal entries are immutable audit pairs and do not consume
    wallet credit a second time.  Any disputed source money left after active
    applications are reopened is recorded as a reversal linked directly to the
    issued origin, which is the only form that reduces available wallet credit.
    """
    remaining = money(amount)
    if remaining == ZERO:
        return
    overpayment = await db.scalar(select(PaymentOverpayment).where(
        PaymentOverpayment.tenant_id == attempt.tenant_id,
        PaymentOverpayment.source_attempt_id == attempt.id,
    ).with_for_update())
    if not overpayment or overpayment.state != "credited":
        return
    origins = (await db.execute(select(CustomerCreditEntry).where(
        CustomerCreditEntry.tenant_id == attempt.tenant_id,
        CustomerCreditEntry.customer_id == attempt.customer_id,
        CustomerCreditEntry.origin_overpayment_id == overpayment.id,
        CustomerCreditEntry.entry_type == "issued",
    ).order_by(CustomerCreditEntry.occurred_at.desc(), CustomerCreditEntry.id.desc()).with_for_update())).scalars().all()
    for origin in origins:
        applications = (await db.execute(select(CustomerCreditEntry).where(
            CustomerCreditEntry.tenant_id == attempt.tenant_id,
            CustomerCreditEntry.customer_id == attempt.customer_id,
            CustomerCreditEntry.source_entry_id == origin.id,
            CustomerCreditEntry.entry_type == "applied",
        ).order_by(CustomerCreditEntry.occurred_at.desc(), CustomerCreditEntry.id.desc()).with_for_update())).scalars().all()
        for application in applications:
            if remaining == ZERO:
                break
            already_reversed = money(await db.scalar(select(func.coalesce(func.sum(CustomerCreditEntry.amount), 0)).where(
                CustomerCreditEntry.tenant_id == attempt.tenant_id,
                CustomerCreditEntry.customer_id == attempt.customer_id,
                CustomerCreditEntry.source_entry_id == application.id,
                CustomerCreditEntry.entry_type == "reversed",
            )))
            active = max(ZERO, money(application.amount) - already_reversed)
            reversal = min(active, remaining)
            if reversal == ZERO:
                continue
            target_settlement = await db.scalar(select(InvoiceSettlement).where(
                InvoiceSettlement.tenant_id == attempt.tenant_id,
                InvoiceSettlement.invoice_id == application.target_invoice_id,
                InvoiceSettlement.customer_id == attempt.customer_id,
            ).with_for_update())
            target_invoice = await db.scalar(select(Invoice).where(
                Invoice.id == application.target_invoice_id,
                Invoice.tenant_id == attempt.tenant_id,
            ).with_for_update())
            target_order = await db.scalar(select(RepairOrder).where(
                RepairOrder.id == (target_invoice.repair_order_id if target_invoice else None),
                RepairOrder.tenant_id == attempt.tenant_id,
            ).with_for_update())
            if not target_settlement or not target_invoice or not target_order:
                raise DB048ReconciliationError(
                    "Disputed customer-credit allocation target is unavailable"
                )
            prior_state = target_settlement.state
            target_settlement.confirmed_principal = max(
                ZERO, money(target_settlement.confirmed_principal) - reversal,
            )
            target_settlement.version += 1
            target_settlement.state = settlement_state(target_settlement)
            target_settlement.accounting_sync_status = "accounting_sync_pending"
            target_invoice.status = (
                InvoiceStatus.OVERDUE
                if target_invoice.due_date
                and target_invoice.due_date < datetime.now(timezone.utc)
                else InvoiceStatus.SENT
            )
            target_invoice.paid_at = None
            target_order.status = RepairOrderStatus.INVOICED
            reversal_entry = CustomerCreditEntry(
                tenant_id=attempt.tenant_id,
                customer_id=attempt.customer_id,
                entry_type="reversed",
                amount=reversal,
                origin_overpayment_id=overpayment.id,
                target_invoice_id=application.target_invoice_id,
                source_entry_id=application.id,
                actor_name_snapshot="Provider reconciliation",
                idempotency_key=f"dispute:{dispute.id}:credit:{application.id}",
                request_hash=hashlib.sha256(json.dumps({
                    "operation": "dispute_credit_reversal",
                    "dispute_id": str(dispute.id),
                    "application_id": str(application.id),
                    "amount": str(reversal),
                }, sort_keys=True).encode()).hexdigest(),
            )
            db.add(reversal_entry)
            application_links = (await db.execute(select(
                PaymentAccountingLink
            ).where(
                PaymentAccountingLink.tenant_id == attempt.tenant_id,
                PaymentAccountingLink.financial_object_type
                == "customer_credit_application",
                PaymentAccountingLink.financial_object_id == application.id,
                PaymentAccountingLink.sync_state != "synced",
            ).with_for_update())).scalars().all()
            for application_link in application_links:
                application_link.sync_state = "superseded"
                application_link.sync_error = (
                    "Source customer credit was reversed by a provider dispute"
                )
            application_outboxes = (await db.execute(select(
                ProviderOutboxEvent
            ).where(
                ProviderOutboxEvent.tenant_id == attempt.tenant_id,
                ProviderOutboxEvent.event_type == CREDIT_ACCOUNTING_EVENT,
                ProviderOutboxEvent.aggregate_id == application.id,
                ProviderOutboxEvent.status.in_([
                    ProviderOutboxStatus.PENDING.value,
                    ProviderOutboxStatus.DEAD.value,
                ]),
            ).with_for_update())).scalars().all()
            for application_outbox in application_outboxes:
                application_outbox.status = ProviderOutboxStatus.EXPIRED.value
                application_outbox.completed_at = datetime.now(timezone.utc)
                application_outbox.last_error = (
                    "Superseded by provider dispute of the source receipt"
                )
            await append_ledger_event(
                db,
                settlement=target_settlement,
                event_type="credit_reversed",
                idempotency_key=f"dispute:{dispute.id}:credit-ledger:{application.id}",
                actor=None,
                prior_state=prior_state,
                new_state=target_settlement.state,
                principal_delta=-reversal,
                evidence={
                    "source_attempt_id": str(attempt.id),
                    "provider_dispute_id": dispute.provider_dispute_id,
                    "credit_application_id": str(application.id),
                },
            )
            remaining = money(remaining - reversal)
        if remaining == ZERO:
            break
        direct_used = money(await db.scalar(select(func.coalesce(func.sum(CustomerCreditEntry.amount), 0)).where(
            CustomerCreditEntry.tenant_id == attempt.tenant_id,
            CustomerCreditEntry.customer_id == attempt.customer_id,
            CustomerCreditEntry.source_entry_id == origin.id,
            CustomerCreditEntry.entry_type.in_(["applied", "refunded", "reversed"]),
        )))
        origin_wallet_remaining = max(ZERO, money(origin.amount) - direct_used)
        wallet_reversal = min(origin_wallet_remaining, remaining)
        if wallet_reversal > ZERO:
            db.add(CustomerCreditEntry(
                tenant_id=attempt.tenant_id,
                customer_id=attempt.customer_id,
                entry_type="reversed",
                amount=wallet_reversal,
                origin_overpayment_id=overpayment.id,
                source_entry_id=origin.id,
                actor_name_snapshot="Provider reconciliation",
                idempotency_key=f"dispute:{dispute.id}:credit-origin:{origin.id}",
                request_hash=hashlib.sha256(json.dumps({
                    "operation": "dispute_credit_origin_reversal",
                    "dispute_id": str(dispute.id),
                    "origin_id": str(origin.id),
                    "amount": str(wallet_reversal),
                }, sort_keys=True).encode()).hexdigest(),
            ))
            remaining = money(remaining - wallet_reversal)
        if remaining == ZERO:
            break
    if remaining != ZERO:
        raise DB048ReconciliationError(
            "Disputed customer credit exceeds the source credit lineage"
        )

    surviving_credit = ZERO
    for origin in origins:
        direct_entries = (await db.execute(select(CustomerCreditEntry).where(
            CustomerCreditEntry.tenant_id == attempt.tenant_id,
            CustomerCreditEntry.customer_id == attempt.customer_id,
            CustomerCreditEntry.source_entry_id == origin.id,
            CustomerCreditEntry.entry_type.in_(["applied", "refunded", "reversed"]),
        ))).scalars().all()
        wallet_remaining = max(
            ZERO,
            money(origin.amount)
            - money(sum((money(entry.amount) for entry in direct_entries), ZERO)),
        )
        active_applications = ZERO
        for entry in direct_entries:
            if entry.entry_type != "applied":
                continue
            reversed_amount = money(await db.scalar(select(func.coalesce(func.sum(CustomerCreditEntry.amount), 0)).where(
                CustomerCreditEntry.tenant_id == attempt.tenant_id,
                CustomerCreditEntry.customer_id == attempt.customer_id,
                CustomerCreditEntry.source_entry_id == entry.id,
                CustomerCreditEntry.entry_type == "reversed",
            )))
            active_applications = money(
                active_applications
                + max(ZERO, money(entry.amount) - reversed_amount)
            )
        surviving_credit = money(
            surviving_credit + wallet_remaining + active_applications
        )
    if surviving_credit == ZERO:
        overpayment.state = "reversed"
        overpayment.resolved_at = datetime.now(timezone.utc)


async def _restore_applied_credit_after_dispute_win(
    db: AsyncSession,
    *,
    attempt: InvoicePaymentAttempt,
    dispute: PaymentProviderDispute,
) -> Decimal:
    """Reapply won-dispute credit to its exact original target invoices.

    A replacement tender may have paid a target while the dispute was open.
    In that case only its current outstanding balance is restored; the rest
    remains source-invoice unapplied money and follows refund-first policy.
    The child `applied` entry is an immutable compensation of the immutable
    dispute reversal, preserving both lineage and deterministic QBO replay.
    """
    reversals = (await db.execute(select(CustomerCreditEntry).where(
        CustomerCreditEntry.tenant_id == attempt.tenant_id,
        CustomerCreditEntry.customer_id == attempt.customer_id,
        CustomerCreditEntry.entry_type == "reversed",
        CustomerCreditEntry.target_invoice_id.is_not(None),
        CustomerCreditEntry.idempotency_key.like(
            f"dispute:{dispute.id}:credit:%"
        ),
    ).order_by(
        CustomerCreditEntry.occurred_at,
        CustomerCreditEntry.id,
    ).with_for_update())).scalars().all()
    restored_total = ZERO
    for reversal in reversals:
        prior_recovery = money(await db.scalar(select(
            func.coalesce(func.sum(CustomerCreditEntry.amount), 0)
        ).where(
            CustomerCreditEntry.tenant_id == attempt.tenant_id,
            CustomerCreditEntry.customer_id == attempt.customer_id,
            CustomerCreditEntry.entry_type == "applied",
            CustomerCreditEntry.source_entry_id == reversal.id,
        )))
        recoverable = max(ZERO, money(reversal.amount) - prior_recovery)
        if recoverable == ZERO:
            continue
        target_settlement = await db.scalar(select(InvoiceSettlement).where(
            InvoiceSettlement.tenant_id == attempt.tenant_id,
            InvoiceSettlement.invoice_id == reversal.target_invoice_id,
            InvoiceSettlement.customer_id == attempt.customer_id,
        ).with_for_update())
        target_invoice = await db.scalar(select(Invoice).where(
            Invoice.id == reversal.target_invoice_id,
            Invoice.tenant_id == attempt.tenant_id,
        ).with_for_update())
        target_order = await db.scalar(select(RepairOrder).where(
            RepairOrder.id == (
                target_invoice.repair_order_id if target_invoice else None
            ),
            RepairOrder.tenant_id == attempt.tenant_id,
            RepairOrder.customer_id == attempt.customer_id,
        ).with_for_update())
        if not target_settlement or not target_invoice or not target_order:
            raise DB048ReconciliationError(
                "Dispute recovery credit target is unavailable"
            )
        outstanding = max(
            ZERO,
            money(target_settlement.principal_total)
            - money(target_settlement.confirmed_principal),
        )
        restored = min(recoverable, outstanding)
        if restored == ZERO:
            continue
        recovery = CustomerCreditEntry(
            tenant_id=attempt.tenant_id,
            customer_id=attempt.customer_id,
            entry_type="applied",
            amount=restored,
            origin_overpayment_id=reversal.origin_overpayment_id,
            target_invoice_id=reversal.target_invoice_id,
            source_entry_id=reversal.id,
            actor_name_snapshot="Provider reconciliation",
            idempotency_key=(
                f"dispute:{dispute.id}:credit-recovery:{reversal.id}"
            ),
            request_hash=hashlib.sha256(json.dumps({
                "operation": "dispute_credit_recovery",
                "dispute_id": str(dispute.id),
                "reversal_id": str(reversal.id),
                "target_invoice_id": str(reversal.target_invoice_id),
                "amount": str(restored),
            }, sort_keys=True).encode()).hexdigest(),
        )
        db.add(recovery)
        prior_state = target_settlement.state
        target_settlement.confirmed_principal = money(
            money(target_settlement.confirmed_principal) + restored
        )
        target_settlement.version += 1
        target_settlement.state = settlement_state(target_settlement)
        target_settlement.accounting_sync_status = "accounting_sync_pending"
        if money(target_settlement.confirmed_principal) >= money(
            target_settlement.principal_total
        ):
            target_invoice.status = InvoiceStatus.PAID
            target_invoice.paid_at = target_invoice.paid_at or datetime.now(timezone.utc)
            target_order.status = RepairOrderStatus.PAID
        await append_ledger_event(
            db,
            settlement=target_settlement,
            event_type="credit_applied",
            idempotency_key=(
                f"dispute:{dispute.id}:credit-recovery-ledger:{reversal.id}"
            ),
            actor=None,
            prior_state=prior_state,
            new_state=target_settlement.state,
            principal_delta=restored,
            evidence={
                "source_attempt_id": str(attempt.id),
                "provider_dispute_id": dispute.provider_dispute_id,
                "credit_reversal_id": str(reversal.id),
                "recovery": "dispute_won",
            },
        )
        restored_total = money(restored_total + restored)
    return restored_total


async def record_stripe_dispute(
    db: AsyncSession,
    *,
    provider_account_id: str,
    provider_charge_id: str,
    provider_dispute_id: str,
    provider_event_id: str,
    amount: Decimal,
    currency: str,
    reason: str,
) -> PaymentProviderDispute:
    """Record one signed partial/full dispute and reopen only exact A/R money."""
    if str(currency).upper() != "USD":
        raise DB048ReconciliationError("Stripe dispute currency does not match DB-048")
    attempt = await db.scalar(select(InvoicePaymentAttempt).where(
        InvoicePaymentAttempt.provider == "stripe_connect",
        InvoicePaymentAttempt.provider_account_id == provider_account_id,
        InvoicePaymentAttempt.provider_charge_id == provider_charge_id,
    ).with_for_update())
    if not attempt:
        raise DB048ReconciliationError("Stripe dispute source does not match a DB-048 payment")
    existing = await db.scalar(select(PaymentProviderDispute).where(
        PaymentProviderDispute.provider == "stripe_connect",
        PaymentProviderDispute.provider_account_id == provider_account_id,
        PaymentProviderDispute.provider_dispute_id == provider_dispute_id,
    ).with_for_update())
    disputed_amount = money(amount)
    if existing:
        if (
            existing.attempt_id != attempt.id
            or existing.provider_charge_id != provider_charge_id
            or money(existing.disputed_gross_amount) != disputed_amount
            or existing.currency != "USD"
        ):
            raise DB048ReconciliationError("Stripe dispute identity was reused with different money")
        return existing
    if attempt.state not in {"confirmed", "reversed"}:
        raise DB048ReconciliationError("Only confirmed provider money can be disputed")

    active_disputes = (await db.execute(select(PaymentProviderDispute).where(
        PaymentProviderDispute.tenant_id == attempt.tenant_id,
        PaymentProviderDispute.attempt_id == attempt.id,
        PaymentProviderDispute.state.in_(["open", "lost"]),
    ).with_for_update())).scalars().all()
    succeeded_refunds = money(await db.scalar(select(func.coalesce(func.sum(PaymentRefund.amount), 0)).where(
        PaymentRefund.tenant_id == attempt.tenant_id,
        PaymentRefund.source_attempt_id == attempt.id,
        PaymentRefund.state == "succeeded",
    )))
    pending_refund = await db.scalar(select(PaymentRefund.id).where(
        PaymentRefund.tenant_id == attempt.tenant_id,
        PaymentRefund.source_attempt_id == attempt.id,
        PaymentRefund.state.in_(["pending", "manual_action_required"]),
    ).limit(1))
    if pending_refund:
        raise DB048ReconciliationError(
            "Stripe dispute overlaps an unresolved refund", retryable=True,
        )
    used_principal = money(sum((money(row.reversed_principal_amount) for row in active_disputes), ZERO))
    used_fee = money(sum((money(row.reversed_card_fee_amount) for row in active_disputes), ZERO))
    used_fee_tax = money(sum((money(row.reversed_card_fee_tax_amount) for row in active_disputes), ZERO))
    used_unapplied = money(sum((money(row.reversed_unapplied_amount) for row in active_disputes), ZERO))
    available_principal = max(ZERO, money(attempt.applied_principal_amount) - used_principal)
    available_fee = max(ZERO, money(attempt.applied_card_fee_amount) - used_fee)
    available_fee_tax = max(ZERO, money(attempt.applied_card_fee_tax_amount) - used_fee_tax)
    available_unapplied = max(
        ZERO,
        money(attempt.unapplied_amount) - succeeded_refunds - used_unapplied,
    )
    principal, fee, fee_tax, unapplied = _split_disputed_gross(
        disputed_amount,
        principal=available_principal,
        card_fee=available_fee,
        card_fee_tax=available_fee_tax,
        unapplied=available_unapplied,
    )
    original_unapplied_principal = max(
        ZERO,
        money(attempt.received_amount or attempt.principal_amount)
        - money(attempt.applied_principal_amount),
    )
    original_unearned_surcharge = max(
        ZERO,
        money(attempt.unapplied_amount) - original_unapplied_principal,
    )
    original_unapplied_total = money(
        original_unapplied_principal + original_unearned_surcharge
    )
    if unapplied > ZERO and original_unapplied_total > ZERO:
        reversed_unapplied_principal = min(
            unapplied,
            money(unapplied * original_unapplied_principal / original_unapplied_total),
        )
        reversed_unearned_surcharge = money(
            unapplied - reversed_unapplied_principal
        )
    else:
        reversed_unapplied_principal = reversed_unearned_surcharge = ZERO

    settlement = await db.scalar(select(InvoiceSettlement).where(
        InvoiceSettlement.id == attempt.settlement_id,
        InvoiceSettlement.tenant_id == attempt.tenant_id,
    ).with_for_update())
    invoice = await db.scalar(select(Invoice).where(
        Invoice.id == attempt.invoice_id,
        Invoice.tenant_id == attempt.tenant_id,
    ).with_for_update())
    order = await db.scalar(select(RepairOrder).where(
        RepairOrder.id == (invoice.repair_order_id if invoice else None),
        RepairOrder.tenant_id == attempt.tenant_id,
    ).with_for_update())
    payment = await db.scalar(select(Payment).where(
        Payment.id == attempt.payment_id,
        Payment.tenant_id == attempt.tenant_id,
    ).with_for_update())
    if not settlement or not invoice or not order or not payment:
        raise DB048ReconciliationError("Stripe dispute source projection is incomplete")
    prior_state = settlement.state
    settlement.confirmed_principal = max(
        ZERO, money(settlement.confirmed_principal) - principal,
    )
    settlement.unapplied_credit = max(
        ZERO, money(settlement.unapplied_credit) - unapplied,
    )
    settlement.version += 1
    settlement.state = settlement_state(settlement)
    payment.amount = max(ZERO, money(payment.amount) - principal)
    if principal > ZERO and money(settlement.confirmed_principal) < money(settlement.principal_total):
        invoice.status = (
            InvoiceStatus.OVERDUE
            if invoice.due_date and invoice.due_date < datetime.now(timezone.utc)
            else InvoiceStatus.SENT
        )
        invoice.paid_at = None
        order.status = RepairOrderStatus.INVOICED

    dispute = PaymentProviderDispute(
        tenant_id=attempt.tenant_id,
        attempt_id=attempt.id,
        provider="stripe_connect",
        provider_account_id=provider_account_id,
        provider_dispute_id=provider_dispute_id,
        provider_charge_id=provider_charge_id,
        currency="USD",
        disputed_gross_amount=disputed_amount,
        reversed_principal_amount=principal,
        reversed_card_fee_amount=fee,
        reversed_card_fee_tax_amount=fee_tax,
        reversed_unapplied_amount=unapplied,
        reversed_unapplied_principal_amount=reversed_unapplied_principal,
        reversed_unearned_surcharge_amount=reversed_unearned_surcharge,
        state="open",
        reason=str(reason or "unknown")[:100],
        created_provider_event_id=provider_event_id,
    )
    db.add(dispute)
    await db.flush()
    await _reverse_applied_credit_for_dispute(
        db,
        attempt=attempt,
        dispute=dispute,
        amount=reversed_unapplied_principal,
    )
    remaining_attempt_money = money(
        available_principal + available_fee + available_fee_tax + available_unapplied
        - disputed_amount
    )
    if remaining_attempt_money == ZERO:
        attempt.state = "reversed"
    attempt.version += 1
    await append_ledger_event(
        db,
        settlement=settlement,
        attempt=attempt,
        event_type="payment_reversed",
        idempotency_key=f"stripe-dispute:{provider_account_id}:{provider_dispute_id}:created",
        actor=None,
        prior_state=prior_state,
        new_state=settlement.state,
        principal_delta=-principal,
        unapplied_delta=-unapplied,
        evidence={
            "provider_dispute_id": provider_dispute_id,
            "provider_event_id": provider_event_id,
            "disputed_gross": str(disputed_amount),
            "reversed_principal": str(principal),
            "reversed_card_fee": str(fee),
            "reversed_card_fee_tax": str(fee_tax),
            "reversed_unapplied": str(unapplied),
            "reversed_unapplied_principal": str(reversed_unapplied_principal),
            "reversed_unearned_surcharge": str(reversed_unearned_surcharge),
            "reason": str(reason or "unknown")[:100],
        },
    )
    config = await db.scalar(select(TenantPaymentProviderConfiguration).where(
        TenantPaymentProviderConfiguration.tenant_id == attempt.tenant_id,
        TenantPaymentProviderConfiguration.version == attempt.provider_configuration_version,
        TenantPaymentProviderConfiguration.selected_provider == "stripe_connect",
        TenantPaymentProviderConfiguration.provider_account_snapshot == provider_account_id,
    ))
    if not config:
        raise DB048ReconciliationError("Stripe dispute configuration snapshot is unavailable")
    link = PaymentAccountingLink(
        tenant_id=attempt.tenant_id,
        invoice_id=attempt.invoice_id,
        attempt_id=attempt.id,
        financial_object_type="payment_dispute",
        financial_object_id=dispute.id,
        operation_version=1,
        principal_amount_snapshot=principal,
        gross_amount_snapshot=disputed_amount,
        owning_writer=config.writer_strategy,
        account_mapping_snapshot=_configuration_mapping_snapshot(config),
        qbo_realm_snapshot=config.qbo_realm_snapshot,
        sync_state="pending",
    )
    db.add(link)
    await db.flush()
    db.add(ProviderOutboxEvent(
        tenant_id=attempt.tenant_id,
        event_type=DISPUTE_ACCOUNTING_EVENT,
        aggregate_type="payment_provider_dispute",
        aggregate_id=dispute.id,
        payload={
            "accounting_link_id": str(link.id),
            "attempt_id": str(attempt.id),
            "invoice_id": str(attempt.invoice_id),
            "dispute_id": str(dispute.id),
        },
        idempotency_key=f"payment-dispute:{dispute.id}:accounting:v1",
        status=ProviderOutboxStatus.PENDING.value,
        available_at=datetime.now(timezone.utc),
    ))
    settlement.accounting_sync_status = "accounting_sync_pending"
    return dispute


async def close_stripe_dispute(
    db: AsyncSession,
    *,
    provider_account_id: str,
    provider_charge_id: str,
    provider_dispute_id: str,
    provider_event_id: str,
    amount: Decimal,
    currency: str,
    outcome: str,
) -> PaymentProviderDispute:
    """Apply a signed terminal dispute outcome, restoring exact won money."""
    dispute = await db.scalar(select(PaymentProviderDispute).where(
        PaymentProviderDispute.provider == "stripe_connect",
        PaymentProviderDispute.provider_account_id == provider_account_id,
        PaymentProviderDispute.provider_dispute_id == provider_dispute_id,
        PaymentProviderDispute.provider_charge_id == provider_charge_id,
    ).with_for_update())
    if (
        not dispute
        or str(currency).upper() != dispute.currency
        or money(amount) != money(dispute.disputed_gross_amount)
    ):
        raise DB048ReconciliationError("Stripe dispute close identity or money does not match")
    normalized = str(outcome).casefold()
    terminal = "won" if normalized == "won" else "lost" if normalized == "lost" else None
    if terminal is None:
        raise DB048ReconciliationError("Stripe dispute close outcome is unsupported")
    if dispute.state in {"won", "lost"}:
        if dispute.state != terminal:
            raise DB048ReconciliationError("Stripe dispute terminal outcome changed")
        return dispute
    attempt = await db.scalar(select(InvoicePaymentAttempt).where(
        InvoicePaymentAttempt.id == dispute.attempt_id,
        InvoicePaymentAttempt.tenant_id == dispute.tenant_id,
        InvoicePaymentAttempt.provider == "stripe_connect",
        InvoicePaymentAttempt.provider_account_id == provider_account_id,
        InvoicePaymentAttempt.provider_charge_id == provider_charge_id,
    ).with_for_update())
    if not attempt:
        raise DB048ReconciliationError("Stripe dispute attempt identity does not match")
    dispute.state = terminal
    dispute.closed_provider_event_id = provider_event_id
    dispute.closed_at = datetime.now(timezone.utc)
    if terminal == "lost":
        return dispute

    settlement = await db.scalar(select(InvoiceSettlement).where(
        InvoiceSettlement.id == attempt.settlement_id,
        InvoiceSettlement.tenant_id == attempt.tenant_id,
    ).with_for_update())
    invoice = await db.scalar(select(Invoice).where(
        Invoice.id == attempt.invoice_id,
        Invoice.tenant_id == attempt.tenant_id,
    ).with_for_update())
    order = await db.scalar(select(RepairOrder).where(
        RepairOrder.id == (invoice.repair_order_id if invoice else None),
        RepairOrder.tenant_id == attempt.tenant_id,
    ).with_for_update())
    payment = await db.scalar(select(Payment).where(
        Payment.id == attempt.payment_id,
        Payment.tenant_id == attempt.tenant_id,
    ).with_for_update())
    if not settlement or not invoice or not order or not payment:
        raise DB048ReconciliationError("Stripe dispute recovery projection is incomplete")
    prior_state = settlement.state
    outstanding = max(ZERO, money(settlement.principal_total) - money(settlement.confirmed_principal))
    restored_principal = min(money(dispute.reversed_principal_amount), outstanding)
    excess_principal = money(dispute.reversed_principal_amount) - restored_principal
    recovered_fee = money(dispute.reversed_card_fee_amount)
    recovered_fee_tax = money(dispute.reversed_card_fee_tax_amount)
    reversed_principal = money(dispute.reversed_principal_amount)
    if reversed_principal > ZERO and restored_principal < reversed_principal:
        earned_recovered_fee = money(recovered_fee * restored_principal / reversed_principal)
        earned_recovered_fee_tax = money(
            recovered_fee_tax * restored_principal / reversed_principal
        )
    elif restored_principal == ZERO:
        earned_recovered_fee = earned_recovered_fee_tax = ZERO
    else:
        earned_recovered_fee = recovered_fee
        earned_recovered_fee_tax = recovered_fee_tax
    unearned_recovered_fee = money(recovered_fee - earned_recovered_fee)
    unearned_recovered_fee_tax = money(recovered_fee_tax - earned_recovered_fee_tax)
    restored_credit_applications = await _restore_applied_credit_after_dispute_win(
        db,
        attempt=attempt,
        dispute=dispute,
    )
    if restored_credit_applications > money(
        dispute.reversed_unapplied_principal_amount
    ):
        raise DB048ReconciliationError(
            "Dispute credit recovery exceeds reversed customer-credit principal"
        )
    restored_unapplied = money(
        money(dispute.reversed_unapplied_amount)
        + excess_principal
        + unearned_recovered_fee
        + unearned_recovered_fee_tax
        - restored_credit_applications
    )
    settlement.confirmed_principal = money(settlement.confirmed_principal) + restored_principal
    settlement.unapplied_credit = money(settlement.unapplied_credit) + restored_unapplied
    settlement.version += 1
    payment.amount = money(payment.amount) + restored_principal
    attempt.state = "confirmed"
    attempt.version += 1
    if money(settlement.confirmed_principal) >= money(settlement.principal_total):
        invoice.status = InvoiceStatus.PAID
        invoice.paid_at = invoice.paid_at or datetime.now(timezone.utc)
        order.status = RepairOrderStatus.PAID
    settlement.state = settlement_state(settlement)
    await append_ledger_event(
        db,
        settlement=settlement,
        attempt=attempt,
        event_type="payment_confirmed",
        idempotency_key=f"stripe-dispute:{provider_account_id}:{provider_dispute_id}:won",
        actor=None,
        prior_state=prior_state,
        new_state=settlement.state,
        principal_delta=restored_principal,
        unapplied_delta=restored_unapplied,
        evidence={
            "provider_dispute_id": provider_dispute_id,
            "provider_event_id": provider_event_id,
            "recovery": "dispute_won",
            "restored_gross": str(money(dispute.disputed_gross_amount)),
            "restored_principal": str(restored_principal),
            "restored_credit_applications": str(restored_credit_applications),
            "unapplied_recovery": str(restored_unapplied),
            "earned_recovered_card_fee": str(earned_recovered_fee),
            "earned_recovered_card_fee_tax": str(earned_recovered_fee_tax),
            "unearned_recovered_card_fee": str(unearned_recovered_fee),
            "unearned_recovered_card_fee_tax": str(unearned_recovered_fee_tax),
        },
    )
    overpayment = await db.scalar(select(PaymentOverpayment).where(
        PaymentOverpayment.tenant_id == attempt.tenant_id,
        PaymentOverpayment.source_attempt_id == attempt.id,
    ).with_for_update())
    if (
        restored_credit_applications > ZERO
        and restored_unapplied == ZERO
        and overpayment is not None
    ):
        overpayment.state = "credited"
        overpayment.resolved_at = datetime.now(timezone.utc)
    if restored_unapplied > ZERO:
        if overpayment is None:
            overpayment = PaymentOverpayment(
                tenant_id=attempt.tenant_id,
                invoice_id=attempt.invoice_id,
                settlement_id=settlement.id,
                source_attempt_id=attempt.id,
                customer_id=attempt.customer_id,
                amount=restored_unapplied,
                state="refund_required",
            )
            db.add(overpayment)
            await db.flush()
        elif overpayment.state in {"reversed", "refunded"}:
            # This is a mutable resolution projection; the signed recovery and
            # exact delta remain immutable in the settlement ledger/dispute.
            overpayment.amount = money(overpayment.amount) + restored_unapplied
            overpayment.state = "refund_required"
            overpayment.resolved_at = None
        active_refund = await db.scalar(select(PaymentRefund).where(
            PaymentRefund.tenant_id == attempt.tenant_id,
            PaymentRefund.overpayment_id == overpayment.id,
            PaymentRefund.state.in_(["pending", "manual_action_required", "failed"]),
        ).with_for_update())
        if active_refund is None:
            refund = PaymentRefund(
                tenant_id=attempt.tenant_id,
                invoice_id=attempt.invoice_id,
                source_attempt_id=attempt.id,
                overpayment_id=overpayment.id,
                amount=restored_unapplied,
                reason="Dispute win restored money above the remaining invoice balance",
                destination_rail="card",
                mode="automatic",
                state="pending",
                actor_name_snapshot="Provider reconciliation",
                idempotency_key=f"dispute-win:{dispute.id}:refund:v1",
                request_hash=hashlib.sha256(json.dumps({
                    "operation": "dispute_win_overpayment_refund",
                    "dispute_id": str(dispute.id),
                    "amount": str(restored_unapplied),
                }, sort_keys=True).encode()).hexdigest(),
            )
            db.add(refund)
            await db.flush()
            settlement.refund_pending = money(settlement.refund_pending) + restored_unapplied
            settlement.state = settlement_state(settlement)
            await append_ledger_event(
                db,
                settlement=settlement,
                attempt=attempt,
                event_type="overpayment_detected",
                idempotency_key=f"dispute-win:{dispute.id}:overpayment",
                actor=None,
                unapplied_delta=restored_unapplied,
                evidence={
                    "overpayment_id": str(overpayment.id),
                    "provider_dispute_id": provider_dispute_id,
                    "origin": "dispute_won_after_replacement_tender",
                },
            )
            await append_ledger_event(
                db,
                settlement=settlement,
                attempt=attempt,
                event_type="refund_requested",
                idempotency_key=f"refund:{refund.id}:requested",
                actor=None,
                refund_pending_delta=restored_unapplied,
                evidence={"refund_id": str(refund.id), "mode": "automatic"},
            )
            db.add(ProviderOutboxEvent(
                tenant_id=attempt.tenant_id,
                event_type=PROVIDER_REFUND_EVENT,
                aggregate_type="payment_refund",
                aggregate_id=refund.id,
                payload={
                    "refund_id": str(refund.id),
                    "attempt_id": str(attempt.id),
                    "amount": str(restored_unapplied),
                },
                idempotency_key=(
                    f"refund:{refund.id}:stripe_connect:{provider_account_id}"
                ),
                status=ProviderOutboxStatus.PENDING.value,
                available_at=datetime.now(timezone.utc),
            ))
    config = await db.scalar(select(TenantPaymentProviderConfiguration).where(
        TenantPaymentProviderConfiguration.tenant_id == attempt.tenant_id,
        TenantPaymentProviderConfiguration.version == attempt.provider_configuration_version,
        TenantPaymentProviderConfiguration.selected_provider == "stripe_connect",
        TenantPaymentProviderConfiguration.provider_account_snapshot == provider_account_id,
    ))
    if not config:
        raise DB048ReconciliationError("Stripe dispute configuration snapshot is unavailable")
    link = PaymentAccountingLink(
        tenant_id=attempt.tenant_id,
        invoice_id=attempt.invoice_id,
        attempt_id=attempt.id,
        financial_object_type="payment_dispute_recovery",
        financial_object_id=dispute.id,
        operation_version=1,
        principal_amount_snapshot=restored_principal,
        gross_amount_snapshot=money(dispute.disputed_gross_amount),
        owning_writer=config.writer_strategy,
        account_mapping_snapshot=_configuration_mapping_snapshot(config),
        qbo_realm_snapshot=config.qbo_realm_snapshot,
        sync_state="pending",
    )
    db.add(link)
    await db.flush()
    db.add(ProviderOutboxEvent(
        tenant_id=attempt.tenant_id,
        event_type=DISPUTE_RECOVERY_ACCOUNTING_EVENT,
        aggregate_type="payment_provider_dispute",
        aggregate_id=dispute.id,
        payload={
            "accounting_link_id": str(link.id),
            "attempt_id": str(attempt.id),
            "invoice_id": str(attempt.invoice_id),
            "dispute_id": str(dispute.id),
        },
        idempotency_key=f"payment-dispute:{dispute.id}:recovery:v1",
        status=ProviderOutboxStatus.PENDING.value,
        available_at=datetime.now(timezone.utc),
    ))
    settlement.accounting_sync_status = "accounting_sync_pending"
    return dispute


async def reverse_confirmed_attempt(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    provider_account_id: str,
    provider_charge_id: str,
    provider_event_id: str,
    reason: str,
) -> InvoicePaymentAttempt:
    """Apply a signed dispute/reversal once and reopen local and QBO A/R."""
    attempt = (await db.execute(select(InvoicePaymentAttempt).where(
        InvoicePaymentAttempt.tenant_id == tenant_id,
        InvoicePaymentAttempt.provider == "stripe_connect",
        InvoicePaymentAttempt.provider_account_id == provider_account_id,
        InvoicePaymentAttempt.provider_charge_id == provider_charge_id,
    ))).scalar_one_or_none()
    if not attempt:
        raise DB048ReconciliationError("Reversal source does not match a DB-048 payment")
    settlement = (await db.execute(select(InvoiceSettlement).where(
        InvoiceSettlement.id == attempt.settlement_id,
        InvoiceSettlement.tenant_id == tenant_id,
    ).with_for_update())).scalar_one()
    event_key = f"payment-reversal:{provider_account_id}:{provider_event_id}"
    existing = (await db.execute(select(InvoicePaymentLedgerEvent).where(
        InvoicePaymentLedgerEvent.tenant_id == tenant_id,
        InvoicePaymentLedgerEvent.idempotency_key == event_key,
    ))).scalar_one_or_none()
    if existing or attempt.state == "reversed":
        return attempt
    if attempt.state != "confirmed":
        raise DB048ReconciliationError("Only a confirmed allocation can be reversed")
    invoice = (await db.execute(select(Invoice).where(
        Invoice.id == attempt.invoice_id,
        Invoice.tenant_id == tenant_id,
    ).with_for_update())).scalar_one()
    order = (await db.execute(select(RepairOrder).where(
        RepairOrder.id == invoice.repair_order_id,
        RepairOrder.tenant_id == tenant_id,
    ).with_for_update())).scalar_one()
    prior_state = settlement.state
    applied = money(attempt.applied_principal_amount)
    unapplied = money(attempt.unapplied_amount)
    settlement.confirmed_principal = max(ZERO, money(settlement.confirmed_principal) - applied)
    reopened_credit_settlements: list[InvoiceSettlement] = []
    if unapplied > ZERO:
        settlement.unapplied_credit = max(ZERO, money(settlement.unapplied_credit) - unapplied)
        refunds = (await db.execute(select(PaymentRefund).where(
            PaymentRefund.source_attempt_id == attempt.id,
            PaymentRefund.tenant_id == tenant_id,
            PaymentRefund.state != "succeeded",
        ).with_for_update())).scalars().all()
        for refund in refunds:
            if refund.state in {"pending", "failed", "manual_action_required"}:
                settlement.refund_pending = max(ZERO, money(settlement.refund_pending) - money(refund.amount))
                refund.state = "cancelled"
                refund.completed_at = datetime.now(timezone.utc)
        overpayment = (await db.execute(select(PaymentOverpayment).where(
            PaymentOverpayment.source_attempt_id == attempt.id,
            PaymentOverpayment.tenant_id == tenant_id,
        ).with_for_update())).scalar_one_or_none()
        if overpayment:
            overpayment.state = "reversed"
            overpayment.resolved_at = datetime.now(timezone.utc)
            credit_origins = (await db.execute(select(CustomerCreditEntry).where(
                CustomerCreditEntry.tenant_id == tenant_id,
                CustomerCreditEntry.customer_id == attempt.customer_id,
                CustomerCreditEntry.origin_overpayment_id == overpayment.id,
                CustomerCreditEntry.entry_type == "issued",
            ).with_for_update())).scalars().all()
            for origin in credit_origins:
                linked_entries = (await db.execute(select(CustomerCreditEntry).where(
                    CustomerCreditEntry.tenant_id == tenant_id,
                    CustomerCreditEntry.customer_id == attempt.customer_id,
                    CustomerCreditEntry.source_entry_id == origin.id,
                ).order_by(
                    CustomerCreditEntry.occurred_at,
                    CustomerCreditEntry.id,
                ).with_for_update())).scalars().all()
                applications = [
                    entry for entry in linked_entries
                    if entry.entry_type == "applied" and entry.target_invoice_id is not None
                ]
                for application in applications:
                    target_settlement = await db.scalar(select(InvoiceSettlement).where(
                        InvoiceSettlement.tenant_id == tenant_id,
                        InvoiceSettlement.invoice_id == application.target_invoice_id,
                        InvoiceSettlement.customer_id == attempt.customer_id,
                    ).with_for_update())
                    target_invoice = await db.scalar(select(Invoice).where(
                        Invoice.id == application.target_invoice_id,
                        Invoice.tenant_id == tenant_id,
                    ).with_for_update())
                    target_order = await db.scalar(select(RepairOrder).where(
                        RepairOrder.id == (
                            target_invoice.repair_order_id if target_invoice else None
                        ),
                        RepairOrder.tenant_id == tenant_id,
                    ).with_for_update())
                    if not target_settlement or not target_invoice or not target_order:
                        raise DB048ReconciliationError(
                            "Applied customer credit target does not match the reversed receipt",
                        )
                    prior_target_state = target_settlement.state
                    application_amount = money(application.amount)
                    target_settlement.confirmed_principal = max(
                        ZERO,
                        money(target_settlement.confirmed_principal) - application_amount,
                    )
                    target_settlement.version += 1
                    target_settlement.state = settlement_state(target_settlement)
                    target_settlement.accounting_sync_status = "accounting_sync_pending"
                    if money(target_settlement.confirmed_principal) < money(
                        target_settlement.principal_total
                    ):
                        target_invoice.status = (
                            InvoiceStatus.OVERDUE
                            if target_invoice.due_date
                            and target_invoice.due_date < datetime.now(timezone.utc)
                            else InvoiceStatus.SENT
                        )
                        target_invoice.paid_at = None
                        target_order.status = RepairOrderStatus.INVOICED
                    await append_ledger_event(
                        db,
                        settlement=target_settlement,
                        event_type="credit_reversed",
                        idempotency_key=(
                            f"credit-reversal:{provider_account_id}:"
                            f"{provider_event_id}:{application.id}"
                        ),
                        actor=None,
                        prior_state=prior_target_state,
                        new_state=target_settlement.state,
                        principal_delta=-application_amount,
                        evidence={
                            "credit_id": str(origin.id),
                            "application_id": str(application.id),
                            "source_attempt_id": str(attempt.id),
                            "provider_event_id": provider_event_id,
                            "reason": reason[:100],
                        },
                    )
                    reopened_credit_settlements.append(target_settlement)
                    credit_outboxes = (await db.execute(select(ProviderOutboxEvent).where(
                        ProviderOutboxEvent.tenant_id == tenant_id,
                        ProviderOutboxEvent.event_type == CREDIT_ACCOUNTING_EVENT,
                        ProviderOutboxEvent.aggregate_id == application.id,
                        ProviderOutboxEvent.status.in_([
                            ProviderOutboxStatus.PENDING.value,
                            ProviderOutboxStatus.DEAD.value,
                        ]),
                    ).with_for_update())).scalars().all()
                    for credit_outbox in credit_outboxes:
                        credit_outbox.status = ProviderOutboxStatus.EXPIRED.value
                        credit_outbox.completed_at = datetime.now(timezone.utc)
                        credit_outbox.last_error = (
                            "Superseded by provider reversal of the source receipt"
                        )
                    credit_links = (await db.execute(select(PaymentAccountingLink).where(
                        PaymentAccountingLink.tenant_id == tenant_id,
                        PaymentAccountingLink.financial_object_type
                        == "customer_credit_application",
                        PaymentAccountingLink.financial_object_id == application.id,
                        PaymentAccountingLink.sync_state != "synced",
                    ).with_for_update())).scalars().all()
                    for credit_link in credit_links:
                        credit_link.sync_state = "superseded"
                        credit_link.sync_error = (
                            "Source provider receipt was reversed before credit delivery"
                        )

                # Invalidate the part of the source credit that had not been
                # applied. Applied portions are reopened above; the immutable
                # application rows remain as history and are paired with the
                # credit_reversed audit events.
                already_used = money(sum(
                    (money(entry.amount) for entry in linked_entries),
                    ZERO,
                ))
                origin_remaining = max(ZERO, money(origin.amount) - already_used)
                if origin_remaining > ZERO:
                    db.add(CustomerCreditEntry(
                        tenant_id=tenant_id,
                        customer_id=attempt.customer_id,
                        entry_type="reversed",
                        amount=origin_remaining,
                        origin_overpayment_id=overpayment.id,
                        source_entry_id=origin.id,
                        actor_name_snapshot="Provider reconciliation",
                        idempotency_key=(
                            f"credit-origin-reversal:{provider_account_id}:"
                            f"{provider_event_id}:{origin.id}"
                        ),
                        request_hash=hashlib.sha256(json.dumps({
                            "operation": "provider_credit_reversal",
                            "provider_account_id": provider_account_id,
                            "provider_event_id": provider_event_id,
                            "credit_id": str(origin.id),
                            "amount": str(origin_remaining),
                        }, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
                    ))
    settlement.version += 1
    settlement.state = settlement_state(settlement)
    attempt.state = "reversed"
    attempt.version += 1
    if attempt.payment_id:
        payment = await db.get(Payment, attempt.payment_id)
        if payment:
            payment.status = PaymentStatus.REFUNDED
    invoice.status = (
        InvoiceStatus.OVERDUE
        if invoice.due_date and invoice.due_date < datetime.now(timezone.utc)
        else InvoiceStatus.SENT
    )
    invoice.paid_at = None
    order.status = RepairOrderStatus.INVOICED
    await append_ledger_event(
        db,
        settlement=settlement,
        attempt=attempt,
        event_type="payment_reversed",
        idempotency_key=event_key,
        actor=None,
        prior_state=prior_state,
        new_state=settlement.state,
        principal_delta=-applied,
        unapplied_delta=-unapplied,
        evidence={"reason": reason[:100], "provider_event_id": provider_event_id},
    )
    config = (await db.execute(select(TenantPaymentProviderConfiguration).where(
        TenantPaymentProviderConfiguration.tenant_id == tenant_id,
        TenantPaymentProviderConfiguration.version == attempt.provider_configuration_version,
    ))).scalar_one()
    link = PaymentAccountingLink(
        tenant_id=tenant_id,
        invoice_id=attempt.invoice_id,
        attempt_id=attempt.id,
        financial_object_type="payment_reversal",
        financial_object_id=attempt.id,
        operation_version=attempt.version,
        owning_writer=config.writer_strategy,
        account_mapping_snapshot={
            key: getattr(config, key)
            for key in (
                "stripe_clearing_account", "qbp_clearing_account",
                "check_deposit_account", "zelle_ach_account",
                "card_fee_income_account", "processor_fee_expense_account",
                "sales_tax_liability_account", "checking_account",
            )
        },
        qbo_realm_snapshot=config.qbo_realm_snapshot,
        sync_state="pending",
    )
    source_accounting_link = await db.scalar(select(PaymentAccountingLink).where(
        PaymentAccountingLink.tenant_id == tenant_id,
        PaymentAccountingLink.attempt_id == attempt.id,
        PaymentAccountingLink.financial_object_type == "invoice_payment",
        PaymentAccountingLink.operation_version == 1,
    ))
    if source_accounting_link and source_accounting_link.provider_deposit_id:
        link.provider_deposit_id = source_accounting_link.provider_deposit_id
    db.add(link)
    await db.flush()
    db.add(ProviderOutboxEvent(
        tenant_id=tenant_id,
        event_type=REVERSAL_ACCOUNTING_EVENT,
        aggregate_type="invoice_payment_attempt",
        aggregate_id=attempt.id,
        payload={
            "accounting_link_id": str(link.id),
            "attempt_id": str(attempt.id),
            "invoice_id": str(attempt.invoice_id),
            "provider_event_id": provider_event_id,
        },
        idempotency_key=f"payment-reversal:{tenant_id}:{attempt.id}:{attempt.version}:{provider_account_id}",
        status=ProviderOutboxStatus.PENDING.value,
        available_at=datetime.now(timezone.utc),
    ))
    settlement.accounting_sync_status = "accounting_sync_pending"
    for target_settlement in reopened_credit_settlements:
        target_settlement.accounting_sync_status = "accounting_sync_pending"
    return attempt


PAYOUT_MAPPING_FIELDS = (
    "stripe_clearing_account",
    "qbp_clearing_account",
    "check_deposit_account",
    "zelle_ach_account",
    "card_fee_income_account",
    "processor_fee_expense_account",
    "sales_tax_liability_account",
    "checking_account",
)
PAYOUT_ENTRY_TOTALS = {
    "charge": "gross_receipts",
    "customer_card_fee": "customer_card_fees",
    "card_fee_tax": "card_fee_tax",
    "refund": "refunds",
    "dispute": "disputes",
    "stripe_fee": "processor_fees",
}


def _canonical_json_hash(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode()).hexdigest()


def _payout_mapping_snapshot(
    config: TenantPaymentProviderConfiguration,
) -> dict[str, Optional[str]]:
    return {field: getattr(config, field) for field in PAYOUT_MAPPING_FIELDS}


def _payout_manifest_record(entry: dict[str, Any]) -> dict[str, Any]:
    occurred_at = entry["occurred_at"]
    if isinstance(occurred_at, str):
        try:
            iso_value = (
                f"{occurred_at[:-1]}+00:00"
                if occurred_at.endswith("Z")
                else occurred_at
            )
            occurred_at = datetime.fromisoformat(iso_value)
        except ValueError as exc:
            raise DB048ReconciliationError(
                "Stripe payout entry occurrence time is invalid"
            ) from exc
    if not isinstance(occurred_at, datetime):
        raise DB048ReconciliationError(
            "Stripe payout entry occurrence time is invalid"
        )
    if occurred_at.tzinfo is None:
        occurred_at = occurred_at.replace(tzinfo=timezone.utc)
    return {
        "id": str(entry["id"]),
        "type": str(entry["type"]),
        "amount": str(money(entry["amount"])),
        "attempt_id": str(entry["attempt_id"]) if entry.get("attempt_id") else None,
        "refund_id": str(entry["refund_id"]) if entry.get("refund_id") else None,
        "dispute_id": str(entry["dispute_id"]) if entry.get("dispute_id") else None,
        "occurred_at": occurred_at.astimezone(timezone.utc).isoformat(),
        "provider_configuration_version": int(entry["provider_configuration_version"]),
        "qbo_realm_snapshot": str(entry["qbo_realm_snapshot"]),
        "owning_writer": str(entry["owning_writer"]),
        "account_mapping_hash": str(entry["account_mapping_hash"]),
        "safe_payload_hash": str(entry["safe_payload_hash"]),
    }


def _payout_manifest(entries: list[dict[str, Any]]) -> str:
    records = sorted(
        (_payout_manifest_record(entry) for entry in entries),
        key=lambda item: (item["id"], item["type"]),
    )
    return _canonical_json_hash(records)


async def _payout_configuration_for_attempt(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    provider_account_id: str,
    attempt_id: UUID,
) -> tuple[InvoicePaymentAttempt, TenantPaymentProviderConfiguration]:
    attempt = await db.scalar(select(InvoicePaymentAttempt).where(
        InvoicePaymentAttempt.id == attempt_id,
        InvoicePaymentAttempt.tenant_id == tenant_id,
        InvoicePaymentAttempt.provider == "stripe_connect",
        InvoicePaymentAttempt.provider_account_id == provider_account_id,
    ))
    if attempt is None:
        raise DB048ReconciliationError("Stripe payout source attempt is unavailable")
    config = await db.scalar(select(TenantPaymentProviderConfiguration).where(
        TenantPaymentProviderConfiguration.tenant_id == tenant_id,
        TenantPaymentProviderConfiguration.version
        == attempt.provider_configuration_version,
        TenantPaymentProviderConfiguration.selected_provider == "stripe_connect",
        TenantPaymentProviderConfiguration.provider_account_snapshot
        == provider_account_id,
        TenantPaymentProviderConfiguration.deleted_at.is_(None),
    ))
    if config is None or not config.qbo_realm_snapshot:
        raise DB048ReconciliationError(
            "Stripe payout provider configuration snapshot is unavailable"
        )
    return attempt, config


async def _standalone_fee_configuration(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    provider_account_id: str,
    occurred_at: datetime,
) -> TenantPaymentProviderConfiguration:
    candidates = list((await db.execute(
        select(TenantPaymentProviderConfiguration).where(
            TenantPaymentProviderConfiguration.tenant_id == tenant_id,
            TenantPaymentProviderConfiguration.selected_provider == "stripe_connect",
            TenantPaymentProviderConfiguration.provider_account_snapshot
            == provider_account_id,
            TenantPaymentProviderConfiguration.deleted_at.is_(None),
            TenantPaymentProviderConfiguration.effective_at <= occurred_at,
            or_(
                TenantPaymentProviderConfiguration.deactivated_at.is_(None),
                TenantPaymentProviderConfiguration.deactivated_at > occurred_at,
            ),
        )
    )).scalars().all())
    if len(candidates) != 1 or not candidates[0].qbo_realm_snapshot:
        raise DB048ReconciliationError(
            "Standalone Stripe fee does not resolve to one historical configuration"
        )
    return candidates[0]


async def _preflight_payout_entries(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    provider_account_id: str,
    payout_id: str,
    entries: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Resolve every provider row to immutable local accounting identity.

    Nothing is inserted until every row and every source/configuration
    relationship has passed this preflight.
    """
    if not entries:
        raise DB048ReconciliationError("Stripe payout contains no reconcilable entries")
    normalized: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for raw in entries:
        entry_type = str(raw.get("type") or "")
        entry_id = str(raw.get("id") or "")
        if entry_type not in PAYOUT_ENTRY_TOTALS or not entry_id or entry_id in seen_ids:
            raise DB048ReconciliationError("Stripe payout entry is invalid")
        seen_ids.add(entry_id)
        try:
            amount = money(raw.get("amount"))
        except Exception as exc:
            raise DB048ReconciliationError("Stripe payout entry amount is invalid") from exc
        if amount <= ZERO:
            raise DB048ReconciliationError("Stripe payout entry amount is invalid")
        occurred_at = raw.get("occurred_at")
        if not isinstance(occurred_at, datetime):
            raise DB048ReconciliationError("Stripe payout entry occurrence time is required")
        if occurred_at.tzinfo is None:
            occurred_at = occurred_at.replace(tzinfo=timezone.utc)
        occurred_at = occurred_at.astimezone(timezone.utc)

        attempt: Optional[InvoicePaymentAttempt] = None
        refund: Optional[PaymentRefund] = None
        dispute: Optional[PaymentProviderDispute] = None
        config: Optional[TenantPaymentProviderConfiguration] = None
        raw_attempt_id = raw.get("attempt_id")
        if raw_attempt_id:
            try:
                attempt_uuid = UUID(str(raw_attempt_id))
            except (TypeError, ValueError) as exc:
                raise DB048ReconciliationError("Stripe payout source attempt is invalid") from exc
            attempt, config = await _payout_configuration_for_attempt(
                db,
                tenant_id=tenant_id,
                provider_account_id=provider_account_id,
                attempt_id=attempt_uuid,
            )

        if entry_type in {"charge", "customer_card_fee", "card_fee_tax"}:
            if attempt is None:
                raise DB048ReconciliationError("Stripe payout entry lacks its source attempt")
            if entry_type == "customer_card_fee" and amount != money(
                attempt.applied_card_fee_amount
            ):
                raise DB048ReconciliationError("Stripe payout customer fee source does not match")
            if entry_type == "card_fee_tax" and amount != money(
                attempt.applied_card_fee_tax_amount
            ):
                raise DB048ReconciliationError("Stripe payout card-fee tax source does not match")
        elif entry_type == "refund":
            try:
                refund_uuid = UUID(str(raw.get("refund_id")))
            except (TypeError, ValueError) as exc:
                raise DB048ReconciliationError("Stripe payout refund source is invalid") from exc
            refund = await db.scalar(select(PaymentRefund).where(
                PaymentRefund.id == refund_uuid,
                PaymentRefund.tenant_id == tenant_id,
                PaymentRefund.provider_reference.is_not(None),
            ))
            if refund is None or amount != money(refund.amount):
                raise DB048ReconciliationError("Stripe payout refund source does not match")
            attempt, config = await _payout_configuration_for_attempt(
                db,
                tenant_id=tenant_id,
                provider_account_id=provider_account_id,
                attempt_id=refund.source_attempt_id,
            )
        elif entry_type == "dispute":
            try:
                dispute_uuid = UUID(str(raw.get("dispute_id")))
            except (TypeError, ValueError) as exc:
                raise DB048ReconciliationError("Stripe payout dispute source is invalid") from exc
            dispute = await db.scalar(select(PaymentProviderDispute).where(
                PaymentProviderDispute.id == dispute_uuid,
                PaymentProviderDispute.tenant_id == tenant_id,
                PaymentProviderDispute.provider == "stripe_connect",
                PaymentProviderDispute.provider_account_id == provider_account_id,
            ))
            if dispute is None or amount != money(dispute.disputed_gross_amount):
                raise DB048ReconciliationError("Stripe payout dispute source does not match")
            attempt, config = await _payout_configuration_for_attempt(
                db,
                tenant_id=tenant_id,
                provider_account_id=provider_account_id,
                attempt_id=dispute.attempt_id,
            )
        elif entry_type == "stripe_fee" and attempt is None:
            config = await _standalone_fee_configuration(
                db,
                tenant_id=tenant_id,
                provider_account_id=provider_account_id,
                occurred_at=occurred_at,
            )
        if config is None:
            raise DB048ReconciliationError(
                "Stripe payout provider configuration snapshot is unavailable"
            )
        mappings = _payout_mapping_snapshot(config)
        mapping_hash = _canonical_json_hash(mappings)
        safe_source = {
            "id": entry_id,
            "type": entry_type,
            "amount": str(amount),
            "attempt_id": str(attempt.id) if attempt else None,
            "refund_id": str(refund.id) if refund else None,
            "dispute_id": str(dispute.id) if dispute else None,
            "occurred_at": occurred_at.isoformat(),
            "provider_configuration_version": config.version,
            "qbo_realm_snapshot": config.qbo_realm_snapshot,
            "owning_writer": config.writer_strategy,
            "account_mapping_hash": mapping_hash,
        }
        normalized.append({
            **safe_source,
            "occurred_at": occurred_at,
            "account_mapping_snapshot": mappings,
            "safe_payload_hash": _canonical_json_hash(safe_source),
        })

    gross_by_attempt: dict[UUID, Decimal] = {}
    for entry in normalized:
        if entry["type"] in {"charge", "customer_card_fee", "card_fee_tax"}:
            attempt_id = UUID(str(entry["attempt_id"]))
            gross_by_attempt[attempt_id] = money(
                gross_by_attempt.get(attempt_id, ZERO) + money(entry["amount"])
            )
    for attempt_id, reconstructed_gross in gross_by_attempt.items():
        attempt = await db.get(InvoicePaymentAttempt, attempt_id)
        if attempt is None or reconstructed_gross != money(attempt.provider_charge_amount):
            raise DB048ReconciliationError(
                "Stripe payout charge components do not match the payment attempt"
            )

    existing_entry = await db.scalar(select(ProviderSettlementEntry).where(
        ProviderSettlementEntry.provider == "stripe_connect",
        ProviderSettlementEntry.provider_account_id == provider_account_id,
        ProviderSettlementEntry.provider_entry_id.in_(seen_ids),
    ).limit(1))
    if existing_entry is not None:
        # An exact payout replay is handled by its immutable batch manifest.
        # A source entry appearing under a new payout is always a collision.
        existing_batch = await db.get(ProviderSettlementBatch, existing_entry.batch_id)
        if (
            existing_batch is None
            or existing_batch.tenant_id != tenant_id
            or existing_batch.provider_batch_id != payout_id
        ):
            raise DB048ReconciliationError("Stripe payout entry identity collision")
    return normalized


async def reconcile_stripe_payout(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    provider_account_id: str,
    payout_id: str,
    net_payout: Decimal,
    entries: list[dict[str, Any]],
) -> ProviderSettlementBatch:
    """Persist a secret-free Stripe payout proof; never create a bank payment."""
    tenant = await db.get(Tenant, tenant_id)
    account_owned = await db.scalar(select(
        TenantPaymentProviderConfiguration.id
    ).where(
        TenantPaymentProviderConfiguration.tenant_id == tenant_id,
        TenantPaymentProviderConfiguration.selected_provider == "stripe_connect",
        TenantPaymentProviderConfiguration.provider_account_snapshot
        == provider_account_id,
        TenantPaymentProviderConfiguration.deleted_at.is_(None),
    ).limit(1))
    if not tenant or account_owned is None:
        raise DB048ReconciliationError("Stripe payout account does not belong to this tenant")
    normalized = await _preflight_payout_entries(
        db,
        tenant_id=tenant_id,
        provider_account_id=provider_account_id,
        payout_id=payout_id,
        entries=entries,
    )
    manifest_hash = _payout_manifest(normalized)
    existing = await db.scalar(select(ProviderSettlementBatch).where(
        ProviderSettlementBatch.provider == "stripe_connect",
        ProviderSettlementBatch.provider_account_id == provider_account_id,
        ProviderSettlementBatch.provider_batch_id == payout_id,
    ))
    if existing:
        if (
            existing.tenant_id != tenant_id
            or money(existing.net_payout) != money(net_payout)
            or existing.entry_manifest_hash != manifest_hash
        ):
            raise DB048ReconciliationError(
                "Stripe payout replay does not match its immutable manifest"
            )
        return existing
    totals = {key: Decimal("0") for key in (
        "gross_receipts", "customer_card_fees", "card_fee_tax", "refunds", "disputes", "processor_fees",
    )}
    for entry in normalized:
        totals[PAYOUT_ENTRY_TOTALS[entry["type"]]] += money(entry["amount"])
    expected = stripe_payout_equation(**totals)
    realms = {str(entry["qbo_realm_snapshot"]) for entry in normalized}
    checking_accounts = {
        str(entry["account_mapping_snapshot"].get("checking_account") or "")
        for entry in normalized
    }
    missing_partition_mapping = any(
        not entry["account_mapping_snapshot"].get("stripe_clearing_account")
        or not entry["account_mapping_snapshot"].get("checking_account")
        or not entry["account_mapping_snapshot"].get("processor_fee_expense_account")
        for entry in normalized
    )
    non_db_writer = any(entry["owning_writer"] != "dieselbridge" for entry in normalized)
    state = "matched" if expected == money(net_payout) else "mismatch"
    mismatch_reason: Optional[str] = (
        None if state == "matched" else f"expected {expected} got {money(net_payout)}"
    )
    if state == "matched" and (
        len(realms) != 1
        or len(checking_accounts) != 1
        or "" in checking_accounts
        or missing_partition_mapping
        or non_db_writer
    ):
        state = "manual_reconciliation_required"
        causes: list[str] = []
        if len(realms) != 1:
            causes.append("mixed_qbo_realms")
        if len(checking_accounts) != 1 or "" in checking_accounts:
            causes.append("mixed_or_missing_checking_accounts")
        if missing_partition_mapping:
            causes.append("incomplete_account_mapping")
        if non_db_writer:
            causes.append("non_dieselbridge_writer")
        mismatch_reason = ",".join(causes)
    batch = ProviderSettlementBatch(
        tenant_id=tenant_id,
        provider="stripe_connect",
        provider_account_id=provider_account_id,
        provider_batch_id=payout_id,
        qbo_realm_snapshot=next(iter(realms)) if len(realms) == 1 else None,
        currency="USD",
        net_payout=money(net_payout),
        entry_manifest_hash=manifest_hash,
        reconciliation_state=state,
        mismatch_reason=mismatch_reason,
        settled_at=datetime.now(timezone.utc),
        **{key: money(value) for key, value in totals.items()},
    )
    db.add(batch)
    await db.flush()
    for entry in normalized:
        db.add(ProviderSettlementEntry(
            tenant_id=tenant_id,
            batch_id=batch.id,
            provider="stripe_connect",
            provider_account_id=provider_account_id,
            provider_entry_id=str(entry["id"]),
            entry_type=str(entry["type"]),
            amount=money(entry["amount"]),
            attempt_id=UUID(str(entry["attempt_id"])) if entry.get("attempt_id") else None,
            refund_id=UUID(str(entry["refund_id"])) if entry.get("refund_id") else None,
            dispute_id=UUID(str(entry["dispute_id"])) if entry.get("dispute_id") else None,
            provider_configuration_version=int(entry["provider_configuration_version"]),
            qbo_realm_snapshot=str(entry["qbo_realm_snapshot"]),
            owning_writer=str(entry["owning_writer"]),
            account_mapping_snapshot=entry["account_mapping_snapshot"],
            account_mapping_hash=str(entry["account_mapping_hash"]),
            occurred_at=entry["occurred_at"],
            safe_payload_hash=str(entry["safe_payload_hash"]),
        ))
    return batch


QBP_NATIVE_FEE_MARKERS = (
    "quickbooks payments fee",
    "system-recorded fee for quickbooks payments",
    "quickbooks payment fee",
)
QBP_NATIVE_VENDOR_MARKERS = (
    "intuit",
    "quickbooks payments",
    "quickbooks payment",
)
QBP_FEE_SETTLEMENT_GRACE_DAYS = 7


def _qbo_native_occurred_at(entity: dict[str, Any]) -> datetime:
    metadata = entity.get("MetaData") if isinstance(entity.get("MetaData"), dict) else {}
    raw = metadata.get("LastUpdatedTime") or metadata.get("CreateTime")
    if raw:
        value = str(raw)
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return (
                parsed.replace(tzinfo=timezone.utc)
                if parsed.tzinfo is None
                else parsed.astimezone(timezone.utc)
            )
        except ValueError:
            pass
    txn_date = str(entity.get("TxnDate") or "")
    try:
        return datetime.fromisoformat(txn_date).replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise DB048ReconciliationError(
            "QuickBooks settlement record has no valid occurrence time"
        ) from exc


def _qbo_ref_value(entity: dict[str, Any], field: str) -> str:
    reference = entity.get(field)
    return str(reference.get("value") or "") if isinstance(reference, dict) else ""


def _qbo_ref_name(entity: dict[str, Any], field: str) -> str:
    reference = entity.get(field)
    return str(reference.get("name") or "") if isinstance(reference, dict) else ""


def _qbo_linked_payment_ids(deposit: dict[str, Any]) -> list[str]:
    linked_ids: list[str] = []
    for line in deposit.get("Line") or []:
        if not isinstance(line, dict):
            continue
        for linked in line.get("LinkedTxn") or []:
            if (
                isinstance(linked, dict)
                and str(linked.get("TxnType") or "").casefold() == "payment"
                and linked.get("TxnId")
            ):
                linked_ids.append(str(linked["TxnId"]))
    return list(dict.fromkeys(linked_ids))


def _qbo_payment_charge_id(payment: dict[str, Any]) -> str:
    card = payment.get("CreditCardPayment")
    response = card.get("CreditChargeResponse") if isinstance(card, dict) else None
    if isinstance(response, dict) and response.get("CCTransId"):
        return str(response["CCTransId"]).strip()
    reference = str(payment.get("PaymentRefNum") or "").strip()
    if reference.casefold().startswith("qbp "):
        return reference[4:].strip()
    # An ordinary QBO reference is user-controlled bookkeeping text. It may
    # collide with a provider charge ID and is not native QBP identity.
    return ""


def _qbo_linked_invoice_ids(payment: dict[str, Any]) -> set[str]:
    linked_ids: set[str] = set()
    for line in payment.get("Line") or []:
        if not isinstance(line, dict):
            continue
        for linked in line.get("LinkedTxn") or []:
            if (
                isinstance(linked, dict)
                and str(linked.get("TxnType") or "").casefold() == "invoice"
                and linked.get("TxnId")
            ):
                linked_ids.add(str(linked["TxnId"]))
    return linked_ids


def _qbo_purchase_expense_account_refs(
    purchase: dict[str, Any],
) -> set[tuple[str, str]]:
    references: set[tuple[str, str]] = set()
    for line in purchase.get("Line") or []:
        if not isinstance(line, dict):
            continue
        detail = line.get("AccountBasedExpenseLineDetail")
        if not isinstance(detail, dict):
            continue
        reference = detail.get("AccountRef")
        if isinstance(reference, dict):
            references.add((
                str(reference.get("value") or ""),
                str(reference.get("name") or ""),
            ))
    return references


def _qbo_reference_matches_configured_account(
    references: set[tuple[str, str]],
    configured: str,
) -> bool:
    expected = configured.strip().casefold()
    return bool(expected) and any(
        expected == value.strip().casefold()
        or expected == name.strip().casefold()
        for value, name in references
    )


def _qbo_is_native_qbp_fee(purchase: dict[str, Any]) -> bool:
    searchable = [
        str(purchase.get("PrivateNote") or ""),
        str((purchase.get("EntityRef") or {}).get("name") or ""),
    ]
    for line in purchase.get("Line") or []:
        if isinstance(line, dict):
            searchable.append(str(line.get("Description") or ""))
    normalized = " ".join(searchable).casefold()
    return any(marker in normalized for marker in QBP_NATIVE_FEE_MARKERS)


def _qbo_has_native_qbp_vendor(purchase: dict[str, Any]) -> bool:
    entity = purchase.get("EntityRef")
    if not isinstance(entity, dict):
        return False
    vendor = " ".join((
        str(entity.get("name") or ""),
        str(entity.get("value") or ""),
    )).casefold()
    return any(marker in vendor for marker in QBP_NATIVE_VENDOR_MARKERS)


async def _qbp_attempt_and_configuration(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    realm_id: str,
    charge_id: str,
) -> tuple[Optional[InvoicePaymentAttempt], Optional[TenantPaymentProviderConfiguration]]:
    if not charge_id:
        return None, None
    attempt = await db.scalar(select(InvoicePaymentAttempt).where(
        InvoicePaymentAttempt.tenant_id == tenant_id,
        InvoicePaymentAttempt.provider == "quickbooks_payments",
        InvoicePaymentAttempt.provider_account_id == realm_id,
        InvoicePaymentAttempt.provider_charge_id == charge_id,
        InvoicePaymentAttempt.state.in_(("confirmed", "refunded", "reversed")),
    ))
    if attempt is None:
        return None, None
    config = await db.scalar(select(TenantPaymentProviderConfiguration).where(
        TenantPaymentProviderConfiguration.tenant_id == tenant_id,
        TenantPaymentProviderConfiguration.version
        == attempt.provider_configuration_version,
        TenantPaymentProviderConfiguration.selected_provider
        == "quickbooks_payments",
        TenantPaymentProviderConfiguration.provider_account_snapshot == realm_id,
        TenantPaymentProviderConfiguration.qbo_realm_snapshot == realm_id,
        TenantPaymentProviderConfiguration.deleted_at.is_(None),
    ))
    return (attempt, config) if config is not None else (attempt, None)


async def _qbp_explicit_customer_fee(
    db: AsyncSession, *, connection: QuickBooksConnection, deposit: dict[str, Any],
    payment: dict[str, Any], attempt: InvoicePaymentAttempt,
    config: TenantPaymentProviderConfiguration,
    journals: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Accept only a persisted, explicitly deposited surcharge debit; never a delta."""
    fee = money(attempt.applied_card_fee_amount) + money(attempt.applied_card_fee_tax_amount)
    principal = money(attempt.applied_principal_amount)
    if (attempt.state != "confirmed" or money(attempt.unapplied_amount) != ZERO
            or money(attempt.received_amount) != principal or fee <= ZERO
            or money(payment.get("TotalAmt")) != principal
            or principal + fee != money(attempt.provider_charge_amount)):
        raise DB048ReconciliationError("qbo_explicit_component_amount_mismatch")
    links = list((await db.scalars(select(PaymentAccountingLink).where(
        PaymentAccountingLink.tenant_id == connection.tenant_id,
        PaymentAccountingLink.attempt_id == attempt.id,
        PaymentAccountingLink.invoice_id == attempt.invoice_id,
        PaymentAccountingLink.financial_object_type == "payment",
        PaymentAccountingLink.qbo_realm_snapshot == connection.realm_id,
    ))).all())
    if len(links) != 1 or not links[0].provider_fee_journal_id or links[0].owning_writer != "dieselbridge":
        raise DB048ReconciliationError("qbo_explicit_component_identity_missing")
    link = links[0]
    for key in ("qbp_clearing_account", "card_fee_income_account", "sales_tax_liability_account"):
        if not (link.account_mapping_snapshot or {}).get(key) or link.account_mapping_snapshot[key] != getattr(config, key):
            raise DB048ReconciliationError("qbo_explicit_component_mapping_mismatch")
    journal_id = str(link.provider_fee_journal_id)
    deposit_lines = [(line, txn) for line in deposit.get("Line", [])
                     for txn in line.get("LinkedTxn", [])
                     if txn.get("TxnType") == "JournalEntry" and str(txn.get("TxnId")) == journal_id]
    if len(deposit_lines) != 1:
        raise DB048ReconciliationError("qbo_explicit_component_link_mismatch")
    journal = journals.get(journal_id)
    if journal is None:
        response = await _request(connection, "GET", f"journalentry/{journal_id}")
        journal = response.get("JournalEntry") if isinstance(response, dict) else None
    if not isinstance(journal, dict) or str(journal.get("Id")) != journal_id:
        raise DB048ReconciliationError("qbo_explicit_component_identity_mismatch")
    journal_occurred_at = _qbo_native_occurred_at({"TxnDate": journal.get("TxnDate")})
    local_payment = await db.get(Payment, attempt.payment_id)
    if (local_payment is None or local_payment.tenant_id != connection.tenant_id
            or local_payment.invoice_payment_attempt_id != attempt.id
            or local_payment.invoice_id != attempt.invoice_id):
        raise DB048ReconciliationError("qbo_explicit_component_payment_identity_mismatch")
    expected = next((body for number, body in db048_qbo_adjustment_payloads(
        attempt=attempt, payment=local_payment, mappings=link.account_mapping_snapshot or {},
    ) if number.startswith("F-")), None)
    if expected is None:
        raise DB048ReconciliationError("qbo_explicit_component_identity_missing")
    expected["PrivateNote"] += f"; attempt={attempt.id}"
    for line in expected["Line"]:
        ref = line["JournalEntryLineDetail"]["AccountRef"]
        ref["value"] = await _resolve_qbo_account_reference(connection, ref["value"])
    if _fee_journal_semantics(journal) != _fee_journal_semantics(expected):
        raise DB048ReconciliationError("qbo_explicit_component_semantics_mismatch")
    debit_lines = [line for line in journal["Line"]
                   if line["JournalEntryLineDetail"]["PostingType"] == "Debit"]
    deposit_line, txn = deposit_lines[0]
    if (len(debit_lines) != 1 or not debit_lines[0].get("Id")
            or str(txn.get("TxnLineId") or "") != str(debit_lines[0]["Id"])
            or money(deposit_line.get("Amount")) != fee):
        raise DB048ReconciliationError("qbo_explicit_component_debit_mismatch")
    return {"journal_id": journal_id, "line_id": str(debit_lines[0]["Id"]),
            "amount": fee, "journal": journal, "attempt": attempt, "occurred_at": journal_occurred_at,
            "semantic_hash": _canonical_json_hash({
                "id": journal_id, "line_id": str(debit_lines[0]["Id"]),
                "doc": expected["DocNumber"], "note": expected["PrivateNote"],
                "lines": [(line["JournalEntryLineDetail"]["PostingType"],
                           line["JournalEntryLineDetail"]["AccountRef"]["value"],
                           str(money(line["Amount"]))) for line in expected["Line"]],
            })}


async def reconcile_qbp_native_settlements(
    db: AsyncSession,
    *,
    connection: QuickBooksConnection,
    deposits: list[dict[str, Any]],
    payments: list[dict[str, Any]],
    purchases: list[dict[str, Any]],
    journals: Optional[list[dict[str, Any]]] = None,
) -> dict[str, int]:
    """Import QBO-native QBP deposits and exact fees without creating QBO rows.

    A payout is attributed to DieselBridge only when at least one linked QBO
    Payment resolves to an exact local QBP charge. Mixed or incomplete batches
    remain visible for a CPA but never enter fee-recovery analytics as matched.
    """
    if not connection.tenant_id or not connection.realm_id:
        raise DB048ReconciliationError(
            "QuickBooks settlement import requires a tenant and company realm"
        )
    tenant_id = connection.tenant_id
    realm_id = str(connection.realm_id)
    journal_by_id = {str(j["Id"]): j for j in journals or [] if isinstance(j, dict) and j.get("Id")}
    payment_by_id = {
        str(payment.get("Id")): payment
        for payment in payments
        if isinstance(payment, dict) and payment.get("Id")
    }
    qbp_fees = [
        purchase
        for purchase in purchases
        if isinstance(purchase, dict)
        and purchase.get("Id")
        and _qbo_is_native_qbp_fee(purchase)
    ]
    deposits_per_group: dict[tuple[str, str], int] = {}
    fees_per_group: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for deposit in deposits:
        if not isinstance(deposit, dict):
            continue
        key = (
            str(deposit.get("TxnDate") or ""),
            _qbo_ref_value(deposit, "DepositToAccountRef"),
        )
        deposits_per_group[key] = deposits_per_group.get(key, 0) + 1
    for purchase in qbp_fees:
        key = (
            str(purchase.get("TxnDate") or ""),
            _qbo_ref_value(purchase, "AccountRef"),
        )
        fees_per_group.setdefault(key, []).append(purchase)

    result = {
        "batches": 0,
        "matched": 0,
        "manual": 0,
        "deferred": 0,
        "skipped": 0,
    }
    for deposit in deposits:
        if not isinstance(deposit, dict) or not deposit.get("Id"):
            continue
        deposit_id = str(deposit["Id"])
        linked_payment_ids = _qbo_linked_payment_ids(deposit)
        if not linked_payment_ids:
            result["skipped"] += 1
            continue
        linked_payments: list[dict[str, Any]] = []
        for payment_id in linked_payment_ids:
            payment = payment_by_id.get(payment_id)
            if payment is None:
                response = await _request(connection, "GET", f"payment/{payment_id}")
                candidate = response.get("Payment") if isinstance(response, dict) else None
                if isinstance(candidate, dict):
                    payment = candidate
                    payment_by_id[payment_id] = payment
            if payment is not None:
                linked_payments.append(payment)

        causes: list[str] = []
        explicit_components: list[dict[str, Any]] = []
        journal_links = [txn for line in deposit.get("Line", []) for txn in line.get("LinkedTxn", [])
                         if txn.get("TxnType") == "JournalEntry"]
        if len(linked_payments) != len(linked_payment_ids):
            causes.append("linked_qbo_payment_missing")
        resolved: list[
            tuple[
                dict[str, Any],
                Optional[InvoicePaymentAttempt],
                Optional[TenantPaymentProviderConfiguration],
            ]
        ] = []
        for payment in linked_payments:
            charge_id = _qbo_payment_charge_id(payment)
            attempt, config = await _qbp_attempt_and_configuration(
                db,
                tenant_id=tenant_id,
                realm_id=realm_id,
                charge_id=charge_id,
            )
            resolved.append((payment, attempt, config))
            if attempt is None:
                causes.append("unmatched_qbo_payment")
            elif config is None:
                causes.append("configuration_snapshot_missing")
            else:
                gross_settlement = await db.scalar(select(InvoiceSettlement).where(
                    InvoiceSettlement.tenant_id == tenant_id,
                    InvoiceSettlement.invoice_id == attempt.invoice_id,
                    InvoiceSettlement.id == attempt.settlement_id,
                ))
                gross_composition = getattr(gross_settlement, "accounting_composition_version", None) == "gross_invoice_v1"
                if money(payment.get("TotalAmt")) != money(attempt.provider_charge_amount):
                    if journal_links and not gross_composition:
                        try:
                            if config.writer_strategy != "dieselbridge":
                                raise DB048ReconciliationError("qbo_explicit_component_writer_mismatch")
                            component = await _qbp_explicit_customer_fee(
                                db, connection=connection, deposit=deposit, payment=payment,
                                attempt=attempt, config=config, journals=journal_by_id,
                            )
                            component["config"] = config
                            explicit_components.append(component)
                        except DB048ReconciliationError as exc:
                            causes.append(str(exc))
                        except (InvalidOperation, TypeError, ValueError):
                            causes.append("qbo_explicit_component_malformed")
                    else:
                        causes.append("qbo_payment_amount_mismatch")
                local_payment = await db.scalar(select(Payment).where(
                    Payment.tenant_id == tenant_id,
                    Payment.id == attempt.payment_id,
                    Payment.invoice_id == attempt.invoice_id,
                    Payment.invoice_payment_attempt_id == attempt.id,
                    Payment.quickbooks_charge_id == charge_id,
                ))
                local_invoice = await db.scalar(select(Invoice).where(
                    Invoice.tenant_id == tenant_id,
                    Invoice.id == attempt.invoice_id,
                ))
                local_customer = await db.scalar(select(Customer).where(
                    Customer.tenant_id == tenant_id,
                    Customer.id == attempt.customer_id,
                ))
                qbo_payment_id = str(payment.get("Id") or "")
                if (
                    local_payment is None
                    or not local_payment.quickbooks_payment_id
                    or str(local_payment.quickbooks_payment_id) != qbo_payment_id
                ):
                    causes.append("qbo_payment_identity_mismatch")
                customer_ref = _qbo_ref_value(payment, "CustomerRef")
                if (
                    local_customer is None
                    or not local_customer.quickbooks_customer_id
                    or str(local_customer.quickbooks_customer_id) != customer_ref
                ):
                    causes.append("qbo_payment_customer_mismatch")
                linked_invoice_ids = _qbo_linked_invoice_ids(payment)
                if (
                    local_invoice is None
                    or not local_invoice.quickbooks_invoice_id
                    or (not gross_composition and linked_invoice_ids != {str(local_invoice.quickbooks_invoice_id)})
                ):
                    causes.append("qbo_payment_invoice_mismatch")
                if gross_composition and local_invoice and local_invoice.quickbooks_invoice_id:
                    from app.services.db048_gross_credit_accounting import gross_credit_allocations
                    from app.services.db048_qbo_gross_accounting import _payment_state, _attempt_changes
                    try:
                        changes = await _attempt_changes(db, attempt, realm_id)
                        allocation = money(attempt.applied_principal_amount) + money(attempt.applied_card_fee_amount) + money(attempt.applied_card_fee_tax_amount)
                        allocation += sum((change["principal"] + change["fee"] + change["tax"] for change in changes), ZERO)
                        gross = money(attempt.provider_charge_amount) + sum((change["gross"] for change in changes), ZERO)
                        targets = await gross_credit_allocations(db, attempt=attempt,
                            tenant=await db.get(Tenant, tenant_id), connection=connection, ensure_invoices=False)
                        if allocation:
                            key = str(local_invoice.quickbooks_invoice_id)
                            targets[key] = targets.get(key, ZERO) + allocation
                        allocated = sum(targets.values(), ZERO)
                        expected = {"total":str(money(gross)),
                            "lines":[(key,str(money(value))) for key,value in sorted(targets.items())],
                            "unapplied":str(money(gross-allocated))}
                        if allocation < ZERO or allocated > gross or _payment_state(payment) != expected:
                            raise DB048ReconciliationError("gross allocation mismatch")
                    except (DB048ReconciliationError, InvalidOperation, TypeError, ValueError):
                        causes.append("qbo_gross_payment_allocation_mismatch")
        matched_configs = [config for _, attempt, config in resolved if attempt and config]
        if not matched_configs:
            result["skipped"] += 1
            continue

        deposit_total = money(deposit.get("TotalAmt"))
        payment_total = sum(
            (money(payment.get("TotalAmt")) for payment, _, _ in resolved),
            ZERO,
        )
        if deposit_total <= ZERO:
            causes.append("invalid_deposit_amount")
        component_total = sum((item["amount"] for item in explicit_components), ZERO)
        if journal_links:
            seen = set()
            line_total = ZERO
            for line in deposit.get("Line", []):
                txns = line.get("LinkedTxn", [])
                if len(txns) != 1 or txns[0].get("TxnType") not in ("Payment", "JournalEntry"):
                    causes.append("qbo_explicit_component_unknown_line")
                    continue
                txn = txns[0]
                identity = (txn.get("TxnType"), str(txn.get("TxnId")))
                if identity in seen:
                    causes.append("qbo_explicit_component_duplicate")
                seen.add(identity)
                if txn.get("TxnType") == "Payment":
                    linked = payment_by_id.get(str(txn.get("TxnId")))
                    if linked is None or money(line.get("Amount")) != money(linked.get("TotalAmt")):
                        causes.append("qbo_explicit_component_payment_line_mismatch")
                line_total += money(line.get("Amount"))
            if len(journal_links) != len(explicit_components):
                causes.append("qbo_explicit_component_unmatched_journal")
            if line_total != deposit_total:
                causes.append("qbo_explicit_component_deposit_mismatch")
        if payment_total + component_total != deposit_total:
            causes.append("deposit_payment_amount_mismatch")

        group_key = (
            str(deposit.get("TxnDate") or ""),
            _qbo_ref_value(deposit, "DepositToAccountRef"),
        )
        fee_candidates = fees_per_group.get(group_key, [])
        fee_purchase: Optional[dict[str, Any]] = None
        fee_missing = False
        if deposits_per_group.get(group_key) == 1 and len(fee_candidates) == 1:
            fee_purchase = fee_candidates[0]
        elif not fee_candidates:
            fee_missing = True
        else:
            causes.append("fee_purchase_ambiguous")

        versions = {config.version for config in matched_configs}
        realms = {str(config.qbo_realm_snapshot or "") for config in matched_configs}
        checking_accounts = {
            str(config.checking_account or "") for config in matched_configs
        }
        if len(versions) != 1:
            causes.append("mixed_configuration_versions")
        if realms != {realm_id}:
            causes.append("mixed_or_foreign_qbo_realms")
        if len(checking_accounts) != 1 or "" in checking_accounts:
            causes.append("mixed_or_missing_checking_accounts")
        deposit_account = group_key[1]
        deposit_account_name = _qbo_ref_name(deposit, "DepositToAccountRef")
        if not deposit_account:
            causes.append("deposit_account_missing")
        elif checking_accounts and not any(
            configured == deposit_account
            or (
                deposit_account_name
                and configured.casefold() == deposit_account_name.casefold()
            )
            for configured in checking_accounts
        ):
            causes.append("deposit_account_mismatch")

        config = matched_configs[0]
        normalized_entries: list[dict[str, Any]] = []
        for component in explicit_components:
            entry_config = component["config"]
            entry_mappings = _payout_mapping_snapshot(entry_config)
            normalized_entries.append({
                "id": f"journal:{component['journal_id']}:{component['line_id']}",
                "type": "qbp_customer_fee_journal", "amount": component["amount"],
                "attempt_id": component["attempt"].id, "refund_id": None, "dispute_id": None,
                "occurred_at": component["occurred_at"],
                "provider_configuration_version": entry_config.version,
                "qbo_realm_snapshot": realm_id, "owning_writer": entry_config.writer_strategy,
                "account_mapping_snapshot": entry_mappings,
                "account_mapping_hash": _canonical_json_hash(entry_mappings),
                "safe_payload_hash": component["semantic_hash"],
            })
        if fee_purchase:
            configured_expense = str(config.processor_fee_expense_account or "")
            if not _qbo_reference_matches_configured_account(
                _qbo_purchase_expense_account_refs(fee_purchase),
                configured_expense,
            ):
                causes.append("fee_expense_account_mismatch")
            if not _qbo_has_native_qbp_vendor(fee_purchase):
                causes.append("fee_vendor_identity_mismatch")
            fee_value = money(fee_purchase.get("TotalAmt"))
            if fee_value <= ZERO or fee_value >= deposit_total:
                causes.append("fee_amount_implausible")

        if fee_missing:
            try:
                deposit_date = datetime.fromisoformat(group_key[0]).date()
            except ValueError:
                causes.append("deposit_date_invalid")
                deposit_date = None
            grace_start = (
                datetime.now(timezone.utc) - timedelta(
                    days=QBP_FEE_SETTLEMENT_GRACE_DAYS
                )
            ).date()
            if not causes and deposit_date is not None and deposit_date > grace_start:
                # QBO can publish the Deposit before its companion fee Purchase.
                # Leave no immutable partial manifest; the overlapping daily
                # query will retry this deposit with the completed native set.
                result["deferred"] += 1
                continue
            causes.append("fee_purchase_missing")

        unique_causes = list(dict.fromkeys(causes))
        state = "matched" if not unique_causes else "manual_reconciliation_required"
        fee_amount = money(fee_purchase.get("TotalAmt")) if fee_purchase else ZERO
        net_payout = money(deposit_total - fee_amount) if fee_purchase else ZERO
        mappings = _payout_mapping_snapshot(config)
        mapping_hash = _canonical_json_hash(mappings)
        occurred_at = _qbo_native_occurred_at(deposit)
        for payment, attempt, payment_config in resolved:
            entry_config = payment_config or config
            entry_mappings = _payout_mapping_snapshot(entry_config)
            payment_id = str(payment.get("Id") or "")
            normalized_entries.append({
                "id": f"payment:{payment_id}",
                "type": "qbp_payment",
                "amount": money(payment.get("TotalAmt")),
                "attempt_id": attempt.id if attempt else None,
                "refund_id": None,
                "dispute_id": None,
                "occurred_at": _qbo_native_occurred_at(payment),
                "provider_configuration_version": entry_config.version,
                "qbo_realm_snapshot": realm_id,
                "owning_writer": entry_config.writer_strategy,
                "account_mapping_snapshot": entry_mappings,
                "account_mapping_hash": _canonical_json_hash(entry_mappings),
                "safe_payload_hash": _canonical_json_hash({
                    "qbo_payment_id": payment_id,
                    "charge_id": _qbo_payment_charge_id(payment),
                    "amount": str(money(payment.get("TotalAmt"))),
                }),
            })
        if fee_purchase:
            normalized_entries.append({
                "id": f"fee:{fee_purchase['Id']}",
                "type": "qbp_fee_purchase",
                "amount": fee_amount,
                "attempt_id": None,
                "refund_id": None,
                "dispute_id": None,
                "occurred_at": _qbo_native_occurred_at(fee_purchase),
                "provider_configuration_version": config.version,
                "qbo_realm_snapshot": realm_id,
                "owning_writer": config.writer_strategy,
                "account_mapping_snapshot": mappings,
                "account_mapping_hash": mapping_hash,
                "safe_payload_hash": _canonical_json_hash({
                    "qbo_purchase_id": str(fee_purchase["Id"]),
                    "amount": str(fee_amount),
                }),
            })
        manifest_hash = _payout_manifest(normalized_entries)
        if journal_links:
            # Deposit links are part of the evidence, even zero-value/unknown
            # lines. Do not let an unchanged monetary manifest hide tampering.
            manifest_hash = _canonical_json_hash({
                "entries": manifest_hash,
                "deposit_components": sorted(
                    (_canonical_json_hash({
                        "amount": str(money(line.get("Amount"))),
                        "links": sorted((str(txn.get("TxnType") or ""),
                                         str(txn.get("TxnId") or ""),
                                         str(txn.get("TxnLineId") or ""))
                                        for txn in line.get("LinkedTxn", [])),
                    }) for line in deposit.get("Line", [])),
                ),
            })
        existing = await db.scalar(select(ProviderSettlementBatch).where(
            ProviderSettlementBatch.provider == "quickbooks_payments",
            ProviderSettlementBatch.provider_account_id == realm_id,
            ProviderSettlementBatch.provider_batch_id == deposit_id,
        ))
        if existing:
            if (
                existing.tenant_id != tenant_id
                or existing.entry_manifest_hash != manifest_hash
                or money(existing.net_payout) != net_payout
                or (existing.reconciliation_state == "matched" and state != "matched")
            ):
                raise DB048ReconciliationError(
                    "QuickBooks payout replay does not match its immutable manifest"
                )
            result["batches"] += 1
            result["matched" if existing.reconciliation_state == "matched" else "manual"] += 1
            continue

        reused_ids = set((await db.scalars(select(ProviderSettlementEntry.provider_entry_id).where(
            ProviderSettlementEntry.provider == "quickbooks_payments",
            ProviderSettlementEntry.provider_account_id == realm_id,
            ProviderSettlementEntry.provider_entry_id.in_([entry["id"] for entry in normalized_entries]),
        ))).all())
        if reused_ids:
            unique_causes.append("qbo_settlement_component_already_used")
            state = "manual_reconciliation_required"

        customer_fees = sum(
            (money(attempt.applied_card_fee_amount) for _, attempt, _ in resolved if attempt),
            ZERO,
        )
        fee_tax = sum(
            (
                money(attempt.applied_card_fee_tax_amount)
                for _, attempt, _ in resolved
                if attempt
            ),
            ZERO,
        )
        gross_receipts = money(deposit_total - customer_fees - fee_tax)
        batch = ProviderSettlementBatch(
            tenant_id=tenant_id,
            provider="quickbooks_payments",
            provider_account_id=realm_id,
            provider_batch_id=deposit_id,
            qbo_realm_snapshot=realm_id,
            currency="USD",
            gross_receipts=gross_receipts,
            customer_card_fees=money(customer_fees),
            card_fee_tax=money(fee_tax),
            refunds=ZERO,
            disputes=ZERO,
            processor_fees=fee_amount,
            net_payout=net_payout,
            entry_manifest_hash=manifest_hash,
            reconciliation_state=state,
            qbo_deposit_id=deposit_id,
            mismatch_reason=",".join(unique_causes) or None,
            settled_at=occurred_at,
        )
        db.add(batch)
        await db.flush()
        for entry in normalized_entries:
            if entry["id"] in reused_ids:
                continue
            db.add(ProviderSettlementEntry(
                tenant_id=tenant_id,
                batch_id=batch.id,
                provider="quickbooks_payments",
                provider_account_id=realm_id,
                provider_entry_id=str(entry["id"]),
                entry_type=str(entry["type"]),
                amount=money(entry["amount"]),
                attempt_id=entry["attempt_id"],
                refund_id=None,
                dispute_id=None,
                provider_configuration_version=int(
                    entry["provider_configuration_version"]
                ),
                qbo_realm_snapshot=realm_id,
                owning_writer=str(entry["owning_writer"]),
                account_mapping_snapshot=entry["account_mapping_snapshot"],
                account_mapping_hash=str(entry["account_mapping_hash"]),
                occurred_at=entry["occurred_at"],
                safe_payload_hash=str(entry["safe_payload_hash"]),
            ))
        result["batches"] += 1
        result["matched" if state == "matched" else "manual"] += 1
    return result


def _stripe_value(value: Any, key: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(key, default)
    return getattr(value, key, default)


async def _book_stripe_payout_batch(
    db: AsyncSession,
    *,
    batch: ProviderSettlementBatch,
) -> str:
    if batch.reconciliation_state == "mismatch":
        raise DB048ReconciliationError(
            f"Stripe payout does not reconcile: {batch.mismatch_reason}", retryable=False,
        )
    if batch.reconciliation_state == "manual_reconciliation_required":
        raise DB048ReconciliationError(
            f"Stripe payout requires manual reconciliation: {batch.mismatch_reason}",
            retryable=False,
        )
    if batch.qbo_deposit_id:
        return batch.qbo_deposit_id
    rows = list((await db.execute(select(ProviderSettlementEntry).where(
        ProviderSettlementEntry.tenant_id == batch.tenant_id,
        ProviderSettlementEntry.batch_id == batch.id,
        ProviderSettlementEntry.provider == "stripe_connect",
        ProviderSettlementEntry.provider_account_id == batch.provider_account_id,
    ).order_by(ProviderSettlementEntry.provider_entry_id))).scalars().all())
    if not rows:
        raise DB048ReconciliationError("Stripe payout proof has no immutable entries")
    from app.services.invoice_accounting_policy import require_exportable_invoice
    attempt_ids = {row.attempt_id for row in rows if row.attempt_id}
    source_invoices = list((await db.scalars(select(Invoice).join(
        InvoicePaymentAttempt, InvoicePaymentAttempt.invoice_id == Invoice.id).where(
            Invoice.tenant_id == batch.tenant_id,
            InvoicePaymentAttempt.tenant_id == batch.tenant_id,
            InvoicePaymentAttempt.id.in_(attempt_ids),
        ).order_by(Invoice.id))).all())
    for invoice in source_invoices:
        await require_exportable_invoice(invoice)
    manifest_entries: list[dict[str, Any]] = []
    partitions: dict[tuple[int, str, str, str], dict[str, Any]] = {}
    for row in rows:
        mappings = dict(row.account_mapping_snapshot or {})
        if _canonical_json_hash(mappings) != row.account_mapping_hash:
            raise DB048ReconciliationError("Stripe payout account mapping proof is invalid")
        manifest_entries.append({
            "id": row.provider_entry_id,
            "type": row.entry_type,
            "amount": row.amount,
            "attempt_id": row.attempt_id,
            "refund_id": row.refund_id,
            "dispute_id": row.dispute_id,
            "occurred_at": row.occurred_at,
            "provider_configuration_version": row.provider_configuration_version,
            "qbo_realm_snapshot": row.qbo_realm_snapshot,
            "owning_writer": row.owning_writer,
            "account_mapping_hash": row.account_mapping_hash,
            "safe_payload_hash": row.safe_payload_hash,
        })
        key = (
            int(row.provider_configuration_version),
            str(row.qbo_realm_snapshot),
            str(row.owning_writer),
            str(row.account_mapping_hash),
        )
        partition = partitions.setdefault(key, {
            "mappings": mappings,
            "totals": {name: ZERO for name in (
                "gross_receipts", "customer_card_fees", "card_fee_tax",
                "refunds", "disputes", "processor_fees",
            )},
        })
        partition["totals"][PAYOUT_ENTRY_TOTALS[row.entry_type]] = money(
            partition["totals"][PAYOUT_ENTRY_TOTALS[row.entry_type]]
            + money(row.amount)
        )
    if _payout_manifest(manifest_entries) != batch.entry_manifest_hash:
        raise DB048ReconciliationError("Stripe payout immutable manifest is invalid")

    realms = {key[1] for key in partitions}
    checking_accounts = {
        str(partition["mappings"].get("checking_account") or "")
        for partition in partitions.values()
    }
    invalid_partitions = any(
        key[2] != "dieselbridge"
        or not partition["mappings"].get("stripe_clearing_account")
        or not partition["mappings"].get("processor_fee_expense_account")
        for key, partition in partitions.items()
    )
    if (
        len(realms) != 1
        or len(checking_accounts) != 1
        or "" in checking_accounts
        or invalid_partitions
    ):
        batch.reconciliation_state = "manual_reconciliation_required"
        batch.mismatch_reason = "historical payout partitions cannot share one QBO journal"
        raise DB048ReconciliationError(
            "Stripe payout requires manual reconciliation: historical partition mismatch",
            retryable=False,
        )
    realm = next(iter(realms))
    checking_account = next(iter(checking_accounts))
    if batch.qbo_realm_snapshot != realm:
        raise DB048ReconciliationError("Stripe payout realm proof is invalid")
    connection = await db.scalar(select(QuickBooksConnection).where(
        QuickBooksConnection.tenant_id == batch.tenant_id,
        QuickBooksConnection.status == "connected",
        QuickBooksConnection.deleted_at.is_(None),
        QuickBooksConnection.realm_id == realm,
    ))
    if not connection or not realm or connection.realm_id != realm:
        raise DB048ReconciliationError("Payout accounting configuration is unavailable", retryable=True)
    doc_number = f"P-{batch.provider_batch_id}"[:21]
    identity_note = (
        f"DB-048 Stripe payout={batch.provider_batch_id}; "
        f"account={batch.provider_account_id}; manifest={batch.entry_manifest_hash}; "
        "bank-feed-match-only"
    )
    existing = await _qbo_find_by_doc_number(connection, "JournalEntry", doc_number)
    if existing and existing.get("Id"):
        if identity_note not in str(existing.get("PrivateNote") or ""):
            raise DB048ReconciliationError(
                "QuickBooks payout journal number collides with an unrelated record"
            )
        journal_id = str(existing["Id"])
    else:
        payout_lines: list[dict[str, Any]] = []
        net = money(batch.net_payout)
        if net != ZERO:
            payout_lines.append({
                "Amount": float(abs(net)),
                "DetailType": "JournalEntryLineDetail",
                "JournalEntryLineDetail": {
                    "PostingType": "Debit" if net > ZERO else "Credit",
                    "AccountRef": {"value": checking_account},
                },
            })
        for key in sorted(partitions):
            partition = partitions[key]
            mappings = partition["mappings"]
            totals = partition["totals"]
            processor_fee = money(totals["processor_fees"])
            clearing_flow = money(
                totals["gross_receipts"]
                + totals["customer_card_fees"]
                + totals["card_fee_tax"]
                - totals["refunds"]
                - totals["disputes"]
            )
            description = f"DB-048 config v{key[0]}"
            if processor_fee > ZERO:
                payout_lines.append({
                    "Amount": float(processor_fee),
                    "Description": description,
                    "DetailType": "JournalEntryLineDetail",
                    "JournalEntryLineDetail": {
                        "PostingType": "Debit",
                        "AccountRef": {
                            "value": mappings["processor_fee_expense_account"],
                        },
                    },
                })
            if clearing_flow != ZERO:
                payout_lines.append({
                    "Amount": float(abs(clearing_flow)),
                    "Description": description,
                    "DetailType": "JournalEntryLineDetail",
                    "JournalEntryLineDetail": {
                        "PostingType": "Credit" if clearing_flow > ZERO else "Debit",
                        "AccountRef": {"value": mappings["stripe_clearing_account"]},
                    },
                })
        response = await _request(connection, "POST", "journalentry", json={
            "DocNumber": doc_number,
            "PrivateNote": identity_note,
            "Line": payout_lines,
        }, params={"requestid": _qbo_request_id("payout", batch.id)})
        journal = response.get("JournalEntry") if isinstance(response, dict) else None
        if not isinstance(journal, dict) or not journal.get("Id"):
            raise QuickBooksAccountingError("QuickBooks did not return the Stripe payout transfer")
        journal_id = str(journal["Id"])
    batch.qbo_deposit_id = journal_id
    batch.qbo_journal_id = journal_id
    batch.reconciliation_state = "synced"
    return journal_id


async def _process_stripe_payout_event(
    db: AsyncSession,
    event: ProviderOutboxEvent,
    *,
    list_balance_transactions: Callable[..., Any] = stripe.BalanceTransaction.list,
    retrieve_dispute: Callable[..., Any] = stripe.Dispute.retrieve,
) -> str:
    payload = event.payload or {}
    payout_id = str(payload.get("payout_id") or "")
    provider_account_id = str(payload.get("provider_account_id") or "")
    if not payout_id or not provider_account_id:
        raise DB048ReconciliationError("Stripe payout envelope is invalid")
    tenant = await db.get(Tenant, event.tenant_id)
    historical_config = await db.scalar(
        select(TenantPaymentProviderConfiguration).where(
            TenantPaymentProviderConfiguration.tenant_id == event.tenant_id,
            TenantPaymentProviderConfiguration.selected_provider == "stripe_connect",
            TenantPaymentProviderConfiguration.provider_account_snapshot
            == provider_account_id,
        ).order_by(
            TenantPaymentProviderConfiguration.effective_at.desc(),
            TenantPaymentProviderConfiguration.version.desc(),
        ).limit(1)
    )
    if not tenant or not historical_config:
        raise DB048ReconciliationError("Stripe payout account does not belong to this tenant")
    response = list_balance_transactions(
        payout=payout_id,
        limit=100,
        stripe_account=provider_account_id,
    )
    raw_rows = list(response.auto_paging_iter()) if hasattr(response, "auto_paging_iter") else list(_stripe_value(response, "data", []))
    entries: list[dict[str, Any]] = []
    for row in raw_rows:
        row_type = str(_stripe_value(row, "type", ""))
        row_id = str(_stripe_value(row, "id", ""))
        source = _stripe_value(row, "source")
        source_id = str(_stripe_value(source, "id", source or ""))
        amount = money(Decimal(str(abs(int(_stripe_value(row, "amount", 0))))) / Decimal("100"))
        fee = money(Decimal(str(abs(int(_stripe_value(row, "fee", 0))))) / Decimal("100"))
        occurred_at = datetime.fromtimestamp(
            int(_stripe_value(row, "created", datetime.now(timezone.utc).timestamp())),
            tz=timezone.utc,
        )
        if row_type == "charge":
            attempt = await db.scalar(select(InvoicePaymentAttempt).where(
                InvoicePaymentAttempt.tenant_id == event.tenant_id,
                InvoicePaymentAttempt.provider == "stripe_connect",
                InvoicePaymentAttempt.provider_account_id == provider_account_id,
                InvoicePaymentAttempt.provider_charge_id == source_id,
            ))
            if not attempt:
                raise DB048ReconciliationError("Stripe payout contains an unmatched charge")
            if amount != money(attempt.provider_charge_amount):
                raise DB048ReconciliationError("Stripe payout charge amount does not match the payment attempt")
            # Reconstruct the immutable provider gross exactly once. Earned
            # fee/tax are split into their own accounting categories; any
            # unearned surcharge remains in the base unapplied receipt until
            # its compensating refund, so gross-to-net still balances.
            base_receipt = money(
                money(attempt.provider_charge_amount)
                - money(attempt.applied_card_fee_amount)
                - money(attempt.applied_card_fee_tax_amount)
            )
            entries.append({
                "id": row_id,
                "type": "charge",
                "amount": str(base_receipt),
                "attempt_id": str(attempt.id),
                "occurred_at": occurred_at,
            })
            if money(attempt.applied_card_fee_amount) > ZERO:
                entries.append({"id": f"{row_id}:customer-fee", "type": "customer_card_fee", "amount": str(money(attempt.applied_card_fee_amount)), "attempt_id": str(attempt.id), "occurred_at": occurred_at})
            if money(attempt.applied_card_fee_tax_amount) > ZERO:
                entries.append({"id": f"{row_id}:fee-tax", "type": "card_fee_tax", "amount": str(money(attempt.applied_card_fee_tax_amount)), "attempt_id": str(attempt.id), "occurred_at": occurred_at})
            if fee > ZERO:
                entries.append({"id": f"{row_id}:stripe-fee", "type": "stripe_fee", "amount": str(fee), "attempt_id": str(attempt.id), "occurred_at": occurred_at})
        elif row_type == "refund":
            refund = await db.scalar(select(PaymentRefund).where(
                PaymentRefund.tenant_id == event.tenant_id,
                PaymentRefund.provider_reference == source_id,
            ))
            if not refund:
                raise DB048ReconciliationError("Stripe payout contains an unmatched refund")
            entries.append({"id": row_id, "type": "refund", "amount": str(amount), "refund_id": str(refund.id), "occurred_at": occurred_at})
        elif row_type == "dispute":
            dispute = retrieve_dispute(source_id, stripe_account=provider_account_id)
            charge_id = str(_stripe_value(dispute, "charge", ""))
            local_dispute = await db.scalar(select(PaymentProviderDispute).where(
                PaymentProviderDispute.tenant_id == event.tenant_id,
                PaymentProviderDispute.provider == "stripe_connect",
                PaymentProviderDispute.provider_account_id == provider_account_id,
                PaymentProviderDispute.provider_dispute_id == source_id,
                PaymentProviderDispute.provider_charge_id == charge_id,
            ))
            attempt = await db.scalar(select(InvoicePaymentAttempt).where(
                InvoicePaymentAttempt.id == (
                    local_dispute.attempt_id if local_dispute else None
                ),
                InvoicePaymentAttempt.tenant_id == event.tenant_id,
                InvoicePaymentAttempt.provider_account_id == provider_account_id,
                InvoicePaymentAttempt.provider_charge_id == charge_id,
            ))
            if not local_dispute or not attempt:
                raise DB048ReconciliationError("Stripe payout contains an unmatched dispute")
            entries.append({
                "id": row_id,
                "type": "dispute",
                "amount": str(amount),
                "attempt_id": str(attempt.id),
                "dispute_id": str(local_dispute.id),
                "occurred_at": occurred_at,
            })
        elif row_type == "stripe_fee":
            entries.append({"id": row_id, "type": "stripe_fee", "amount": str(amount), "occurred_at": occurred_at})
        elif row_type == "payout":
            continue
        else:
            raise DB048ReconciliationError(f"Unsupported Stripe payout entry type: {row_type}")
    batch = await reconcile_stripe_payout(
        db,
        tenant_id=event.tenant_id,
        provider_account_id=provider_account_id,
        payout_id=payout_id,
        net_payout=money(payload.get("net_payout")),
        entries=entries,
    )
    # Reconciliation evidence is authoritative provider data and must remain
    # visible even when the downstream QBO write exhausts its retries. Keep
    # the outbox claim processing while committing only this immutable batch;
    # the worker lock-token fence still guards later local finalization.
    await db.commit()
    return await _book_stripe_payout_batch(db, batch=batch)


async def _project_accounting_dead_letter(
    db: AsyncSession,
    event: ProviderOutboxEvent,
) -> None:
    """Surface terminal delivery failure on the financial projection/audit."""
    payload = event.payload or {}
    if event.event_type == PAYOUT_RECONCILIATION_EVENT:
        payout_id = str(payload.get("payout_id") or "")
        provider_account_id = str(payload.get("provider_account_id") or "")
        if not payout_id or not provider_account_id:
            return
        batch = await db.scalar(select(ProviderSettlementBatch).where(
            ProviderSettlementBatch.tenant_id == event.tenant_id,
            ProviderSettlementBatch.provider == "stripe_connect",
            ProviderSettlementBatch.provider_account_id == provider_account_id,
            ProviderSettlementBatch.provider_batch_id == payout_id,
        ).with_for_update())
        if batch and batch.reconciliation_state not in {
            "synced", "mismatch", "manual_reconciliation_required",
        }:
            batch.reconciliation_state = "accounting_failed"
            batch.mismatch_reason = event.last_error
        return
    if event.event_type == PROVIDER_REFUND_EVENT:
        try:
            refund_id = UUID(str(payload.get("refund_id")))
        except (TypeError, ValueError):
            return
        refund = await db.scalar(select(PaymentRefund).where(
            PaymentRefund.id == refund_id,
            PaymentRefund.tenant_id == event.tenant_id,
        ).with_for_update())
        if not refund or refund.state in {"succeeded", "cancelled"}:
            return
        refund.state = "failed"
        refund.last_error = event.last_error
        overpayment = await db.scalar(select(PaymentOverpayment).where(
            PaymentOverpayment.id == refund.overpayment_id,
            PaymentOverpayment.tenant_id == event.tenant_id,
        ).with_for_update())
        if overpayment:
            overpayment.state = "refund_required"
        settlement = await db.scalar(select(InvoiceSettlement).where(
            InvoiceSettlement.tenant_id == event.tenant_id,
            InvoiceSettlement.invoice_id == refund.invoice_id,
        ).with_for_update())
        attempt = await db.scalar(select(InvoicePaymentAttempt).where(
            InvoicePaymentAttempt.id == refund.source_attempt_id,
            InvoicePaymentAttempt.tenant_id == event.tenant_id,
        ))
        if settlement and attempt:
            await append_ledger_event(
                db,
                settlement=settlement,
                attempt=attempt,
                event_type="refund_failed",
                idempotency_key=f"refund-outbox:{event.id}:dead:{event.attempt_count}",
                actor=None,
                evidence={"refund_id": str(refund.id), "retryable": True},
            )
        return

    link_id = payload.get("accounting_link_id")
    if not link_id:
        return
    try:
        link_uuid = UUID(str(link_id))
    except (TypeError, ValueError):
        return
    link = await db.scalar(select(PaymentAccountingLink).where(
        PaymentAccountingLink.id == link_uuid,
        PaymentAccountingLink.tenant_id == event.tenant_id,
    ).with_for_update())
    if not link or link.sync_state == "synced":
        return
    link.sync_state = "dead"
    link.sync_error = event.last_error
    if not link.invoice_id:
        return
    settlement = await db.scalar(select(InvoiceSettlement).where(
        InvoiceSettlement.tenant_id == event.tenant_id,
        InvoiceSettlement.invoice_id == link.invoice_id,
    ).with_for_update())
    if not settlement:
        return
    settlement.accounting_sync_status = "accounting_failed"
    attempt = (
        await db.scalar(select(InvoicePaymentAttempt).where(
            InvoicePaymentAttempt.id == link.attempt_id,
            InvoicePaymentAttempt.tenant_id == event.tenant_id,
        ))
        if link.attempt_id else None
    )
    await append_ledger_event(
        db,
        settlement=settlement,
        attempt=attempt,
        event_type="accounting_failed",
        idempotency_key=f"accounting:{event.id}:dead:{event.attempt_count}",
        actor=None,
        evidence={
            "operation_id": str(link.id),
            "financial_object_type": link.financial_object_type,
            "retryable": True,
        },
    )


async def process_due_db048_outbox_events(
    *,
    session_factory: async_sessionmaker[AsyncSession] = AsyncSessionLocal,
    batch_size: Optional[int] = None,
) -> dict[str, int]:
    """Process a bounded DB-048 accounting/refund batch with durable retries."""
    now = datetime.now(timezone.utc)
    limit = batch_size or settings.PROVIDER_OUTBOX_BATCH_SIZE
    async with session_factory() as db:
        rows = (await db.execute(select(ProviderOutboxEvent).where(
            ProviderOutboxEvent.event_type.in_(WORKER_EVENTS),
            or_(
                and_(ProviderOutboxEvent.status == "pending", ProviderOutboxEvent.available_at <= now),
                and_(ProviderOutboxEvent.status == "processing", ProviderOutboxEvent.locked_until <= now),
            ),
        ).order_by(ProviderOutboxEvent.available_at).limit(limit).with_for_update(skip_locked=True))).scalars().all()
        claims: list[tuple[UUID, str]] = []
        for event in rows:
            event.status = "processing"
            event.attempt_count += 1
            event.lock_token = uuid4().hex
            event.locked_at = now
            event.locked_until = now + timedelta(seconds=settings.PROVIDER_OUTBOX_LEASE_SECONDS)
            claims.append((event.id, event.lock_token))
        await db.commit()
    results = {"claimed": len(claims), "succeeded": 0, "retried": 0, "dead": 0, "lease_lost": 0}
    for event_id, claim_token in claims:
        async with session_factory() as db:
            event = await db.scalar(select(ProviderOutboxEvent).where(
                ProviderOutboxEvent.id == event_id,
                ProviderOutboxEvent.status == "processing",
                ProviderOutboxEvent.lock_token == claim_token,
            ))
            try:
                if not event or event.event_type not in WORKER_EVENTS:
                    raise DB048ReconciliationError("Claimed DB-048 event is invalid")
                if event.event_type == PROVIDER_REFUND_EVENT:
                    provider_id = await _submit_stripe_refund(db, event)
                elif event.event_type == PAYOUT_RECONCILIATION_EVENT:
                    provider_id = await _process_stripe_payout_event(db, event)
                elif event.event_type == CREDIT_ACCOUNTING_EVENT:
                    credit_envelope = await load_credit_accounting_envelope(db, event)
                    await _refresh_accounting_connection_if_needed(
                        db,
                        credit_envelope.connection,
                    )
                    provider_id = await deliver_credit_accounting_envelope(db, credit_envelope)
                else:
                    envelope = await load_accounting_envelope(db, event)
                    await _refresh_accounting_connection_if_needed(
                        db,
                        envelope.connection,
                    )
                    provider_id = await deliver_accounting_envelope(db, envelope)
                # Provider calls can outlive a lease. Do not let an expired
                # worker commit stale local projections after another worker
                # reclaimed the row. Provider-side requestid/idempotency keys
                # make the external replay deterministic; this token is the
                # database-side fencing check.
                with db.no_autoflush:
                    owned = await db.scalar(select(ProviderOutboxEvent.id).where(
                        ProviderOutboxEvent.id == event_id,
                        ProviderOutboxEvent.status == "processing",
                        ProviderOutboxEvent.lock_token == claim_token,
                        ProviderOutboxEvent.locked_until > datetime.now(timezone.utc),
                    ).with_for_update())
                if owned is None:
                    # Retain immutable provider evidence even if this worker
                    # lost its projection lease. Do not update the outbox or
                    # any money/state projection owned by a newer worker.
                    retained = None
                    if event.event_type == PROVIDER_REFUND_EVENT:
                        row = (await db.execute(select(PaymentRefund, InvoicePaymentAttempt).join(
                            InvoicePaymentAttempt, InvoicePaymentAttempt.id == PaymentRefund.source_attempt_id,
                        ).where(
                            PaymentRefund.id == UUID(str((event.payload or {}).get("refund_id"))),
                            PaymentRefund.tenant_id == event.tenant_id,
                            InvoicePaymentAttempt.tenant_id == event.tenant_id,
                            InvoicePaymentAttempt.provider == "quickbooks_payments",
                        ))).first()
                        if row and row[0].provider_reference:
                            retained = (row[0].id, row[0].tenant_id, row[0].source_attempt_id,
                                        row[0].amount, row[0].provider_reference, row[1].provider_charge_id)
                    await db.rollback()
                    if retained:
                        refund_id, tenant_id, attempt_id, amount, reference, charge_id = retained
                        refund_row = await db.scalar(select(PaymentRefund).join(
                            InvoicePaymentAttempt, InvoicePaymentAttempt.id == PaymentRefund.source_attempt_id,
                        ).where(
                            PaymentRefund.id == refund_id, PaymentRefund.tenant_id == tenant_id,
                            PaymentRefund.source_attempt_id == attempt_id, PaymentRefund.amount == amount,
                            InvoicePaymentAttempt.tenant_id == tenant_id,
                            InvoicePaymentAttempt.provider == "quickbooks_payments",
                            InvoicePaymentAttempt.provider_charge_id == charge_id,
                        ).with_for_update())
                        if refund_row and refund_row.provider_reference is None:
                            refund_row.provider_reference = reference
                            await db.commit()
                    results["lease_lost"] += 1
                    continue
                if event.event_type == PROVIDER_REFUND_EVENT:
                    pending_qbp = await db.scalar(select(PaymentRefund).join(
                        InvoicePaymentAttempt, InvoicePaymentAttempt.id == PaymentRefund.source_attempt_id,
                    ).where(
                        PaymentRefund.id == UUID(str((event.payload or {}).get("refund_id"))),
                        PaymentRefund.tenant_id == event.tenant_id,
                        InvoicePaymentAttempt.tenant_id == event.tenant_id,
                        InvoicePaymentAttempt.provider == "quickbooks_payments",
                        PaymentRefund.state == "pending",
                        PaymentRefund.last_error.in_([
                            "qbp_refund_accepted_pending", "qbp_refund_outcome_unknown",
                            "qbp_refund_identity_mismatch", "qbp_refund_amount_mismatch",
                        ]),
                    ))
                    if pending_qbp:
                        # Do not raise/rollback: preserve accepted provider ID
                        # in the same lease-fenced commit as the pending event.
                        event.provider_message_id = pending_qbp.provider_reference
                        event.last_error = pending_qbp.last_error
                        event.lock_token = None
                        event.locked_until = None
                        if pending_qbp.last_error == "qbp_refund_accepted_pending":
                            pending_qbp.retry_count = 0
                            # ISSUED is normal settlement progress, not a
                            # delivery failure. Poll across business-day time
                            # scales rather than exhausting the error budget.
                            created_at = pending_qbp.created_at
                            if created_at.tzinfo is None:
                                created_at = created_at.replace(tzinfo=timezone.utc)
                            if datetime.now(timezone.utc) < created_at + timedelta(days=14):
                                event.status = ProviderOutboxStatus.PENDING.value
                                event.available_at = datetime.now(timezone.utc) + timedelta(hours=6)
                                results["retried"] += 1
                            else:
                                event.status = ProviderOutboxStatus.DEAD.value
                                event.last_error = "qbp_refund_settlement_deadline_requires_reconciliation"
                                event.completed_at = datetime.now(timezone.utc)
                                results["dead"] += 1
                        else:
                            pending_qbp.retry_count = (pending_qbp.retry_count or 0) + 1
                            if pending_qbp.retry_count < settings.PROVIDER_OUTBOX_MAX_ATTEMPTS:
                                event.status = ProviderOutboxStatus.PENDING.value
                                event.available_at = datetime.now(timezone.utc) + timedelta(seconds=300)
                                results["retried"] += 1
                            else:
                                event.status = ProviderOutboxStatus.DEAD.value
                                event.completed_at = datetime.now(timezone.utc)
                                results["dead"] += 1
                        await db.commit()
                        continue
                event.status = ProviderOutboxStatus.SUCCEEDED.value
                event.provider_message_id = provider_id
                event.completed_at = datetime.now(timezone.utc)
                event.lock_token = None
                event.locked_until = None
                event.last_error = None
                await db.commit()
                results["succeeded"] += 1
            except (DB048ReconciliationError, QuickBooksAccountingError) as exc:
                await db.rollback()
                event = await db.scalar(select(ProviderOutboxEvent).where(
                    ProviderOutboxEvent.id == event_id,
                    ProviderOutboxEvent.status == "processing",
                    ProviderOutboxEvent.lock_token == claim_token,
                ).with_for_update())
                retryable = bool(getattr(exc, "retryable", False))
                if event:
                    event.last_error = f"{type(exc).__name__}: {str(exc)[:400]}"
                    event.lock_token = None
                    event.locked_until = None
                    if retryable and event.attempt_count < settings.PROVIDER_OUTBOX_MAX_ATTEMPTS:
                        event.status = ProviderOutboxStatus.PENDING.value
                        event.available_at = datetime.now(timezone.utc) + timedelta(
                            seconds=min(30 * (2 ** max(event.attempt_count - 1, 0)), 3600)
                        )
                        results["retried"] += 1
                    else:
                        event.status = ProviderOutboxStatus.DEAD.value
                        event.completed_at = datetime.now(timezone.utc)
                        await _project_accounting_dead_letter(db, event)
                        results["dead"] += 1
                    await db.commit()
                else:
                    results["lease_lost"] += 1
    return results
