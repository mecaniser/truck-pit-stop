"""Idempotent DB-048 legacy invoice/payment baseline backfill.

The backfill creates factual baseline rows without inventing tender history and
proves on every invocation that the same tenant-scoped source envelope still
maps to the same baseline settlements, attempts, and immutable events. A
previously verified run is therefore a verify-only rerun, not an early return.
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models.invoice import Invoice, InvoiceStatus
from app.db.models.invoice_settlement import (
    InvoicePaymentAttempt,
    InvoicePaymentLedgerEvent,
    InvoiceSettlement,
    InvoiceSettlementBackfillRun,
    TenantPaymentProviderConfiguration,
)
from app.db.models.payment import Payment, PaymentMethod, PaymentStatus
from app.db.models.repair_order import RepairOrder
from app.db.models.tenant import Tenant
from app.services.invoice_settlement_service import (
    ZERO,
    append_ledger_event,
    bind_settlement_accounting_realm,
    current_zelle_attempt_matches,
    invoice_money_snapshot,
    money,
    settlement_state,
)


_SOURCE_CHECKSUM_KEYS = ("invoices", "payments", "pending_zelle")
DEFAULT_BACKFILL_BATCH_SIZE = 100


def _checksum(rows: list[dict[str, Any]]) -> str:
    encoded = json.dumps(rows, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(encoded).hexdigest()


def _enum_value(value: Any) -> Any:
    return getattr(value, "value", value)


def _timestamp(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _legacy_rail(payment: Payment) -> tuple[str | None, str | None, str | None]:
    if payment.method == PaymentMethod.STRIPE:
        return "card", "stripe_connect", payment.stripe_connected_account_id
    if payment.method == PaymentMethod.QUICKBOOKS:
        return "card", "quickbooks_payments", None
    if payment.method == PaymentMethod.ZELLE:
        return "zelle", "manual", None
    if payment.method == PaymentMethod.CHECK:
        return "check", "manual", None
    if payment.method == PaymentMethod.ACH:
        return "ach", "manual", None
    return None, None, None


def _invoice_eligibility(invoice: Invoice) -> tuple[bool, str | None]:
    if invoice.repair_order is None:
        return False, "missing_repair_order"
    if invoice.repair_order.customer_id is None:
        return False, "missing_customer"
    return True, None


def _invoice_source_row(
    invoice: Invoice,
    *,
    eligible: bool,
    ineligible_reason: str | None,
) -> dict[str, Any]:
    principal, fee, fee_tax, tax_rate, fee_rate = invoice_money_snapshot(invoice)
    return {
        "invoice_id": str(invoice.id),
        "repair_order_id": str(invoice.repair_order_id),
        "customer_id": (
            str(invoice.repair_order.customer_id)
            if invoice.repair_order is not None and invoice.repair_order.customer_id is not None
            else None
        ),
        # Invoice status is a derived operational projection.  A native
        # DB-048 confirmation may legitimately move SENT -> PAID after a
        # baseline cutoff without changing any baseline-owned source money.
        # Payment/attempt reciprocity below proves that transition instead of
        # freezing this mutable projection into the legacy source checksum.
        "principal_total": str(principal),
        "max_card_fee": str(fee),
        "max_card_fee_tax": str(fee_tax),
        "sales_tax_rate": str(tax_rate),
        "card_fee_rate": str(fee_rate),
        "eligible": eligible,
        "ineligible_reason": ineligible_reason,
    }


def _payment_source_row(
    payment: Payment,
    *,
    eligible: bool,
    ineligible_reason: str | None,
) -> dict[str, Any]:
    rail, provider, provider_account = _legacy_rail(payment)
    return {
        "payment_id": str(payment.id),
        "invoice_id": str(payment.invoice_id),
        "amount": str(money(payment.amount)),
        "method": _enum_value(payment.method),
        "status": _enum_value(payment.status),
        "created_at": _timestamp(payment.created_at),
        "rail": rail,
        "provider": provider,
        "provider_account": provider_account,
        "provider_intent_id": payment.stripe_payment_intent_id,
        "provider_charge_id": payment.stripe_charge_id or payment.quickbooks_charge_id,
        "provider_reference": payment.reference_number,
        "actor_user_id": str(payment.recorded_by_user_id) if payment.recorded_by_user_id else None,
        "eligible": eligible,
        "ineligible_reason": ineligible_reason,
    }


def _pending_zelle_source_row(
    invoice: Invoice,
    *,
    eligible: bool,
    ineligible_reason: str | None,
) -> dict[str, Any]:
    submitted_at = invoice.zelle_pending_submitted_at
    expires_at = submitted_at + timedelta(hours=24) if submitted_at else None
    return {
        "invoice_id": str(invoice.id),
        "submitted_at": _timestamp(submitted_at),
        "expires_at": _timestamp(expires_at),
        "sender_email_present": bool(invoice.zelle_pending_sender_email),
        "sender_phone_present": bool(invoice.zelle_pending_sender_phone),
        "eligible": eligible,
        "ineligible_reason": ineligible_reason,
    }


def _baseline_plan(
    *,
    invoices: list[Invoice],
    payments_by_invoice: dict[UUID, list[Payment]],
    linked_attempts: dict[UUID, InvoicePaymentAttempt],
    linked_zelle_attempts: dict[UUID, InvoicePaymentAttempt],
    settlements_by_invoice: dict[UUID, InvoiceSettlement],
    cutoff_at: datetime,
) -> dict[UUID, dict[str, Any]]:
    """Build the deterministic source-to-baseline plan for eligible invoices."""
    plan: dict[UUID, dict[str, Any]] = {}
    for invoice in invoices:
        principal, *_ = invoice_money_snapshot(invoice)
        existing_settlement = settlements_by_invoice.get(invoice.id)
        confirmed = money(existing_settlement.confirmed_principal) if existing_settlement else ZERO
        unapplied = ZERO
        payment_rows: list[dict[str, Any]] = []
        attempt_keys: list[str] = []
        event_keys: list[str] = []

        for payment in payments_by_invoice.get(invoice.id, []):
            linked_attempt = linked_attempts.get(payment.id)
            if linked_attempt is not None:
                if linked_attempt.source == "backfill":
                    attempt_keys.append(linked_attempt.idempotency_key)
                    event_keys.append(f"backfill:payment:{payment.id}:event")
                payment_rows.append({
                    "payment": payment,
                    "linked_attempt": linked_attempt,
                    "received": money(payment.amount),
                    "refunded": payment.status == PaymentStatus.REFUNDED,
                    "valid_amount": money(payment.amount) > ZERO,
                    "applied": ZERO,
                    "excess": ZERO,
                })
                continue
            received = money(payment.amount)
            refunded = payment.status == PaymentStatus.REFUNDED
            rail, _provider, _provider_account = _legacy_rail(payment)
            valid_amount = received > ZERO
            remaining = max(ZERO, money(principal) - money(confirmed))
            applied = ZERO if refunded or not valid_amount else min(received, remaining)
            excess = ZERO if refunded or not valid_amount else money(received - applied)
            if valid_amount:
                confirmed = money(confirmed + applied)
                unapplied = money(unapplied + excess)
            if valid_amount and rail:
                attempt_keys.append(f"backfill:payment:{payment.id}")
            event_keys.append(f"backfill:payment:{payment.id}:event")
            payment_rows.append({
                "payment": payment,
                "linked_attempt": None,
                "received": received,
                "refunded": refunded,
                "valid_amount": valid_amount,
                "applied": applied,
                "excess": excess,
            })

        paid_snapshot_delta = ZERO
        if invoice.status == InvoiceStatus.PAID:
            paid_key = f"backfill:invoice:{invoice.id}:paid-baseline"
            if confirmed < money(principal):
                paid_snapshot_delta = money(principal - confirmed)
                confirmed = money(principal)
                event_keys.append(paid_key)
            elif (
                existing_settlement is not None
                and existing_settlement.legacy_reconciliation_status
                == "legacy_paid_without_tender"
            ):
                event_keys.append(paid_key)

        zelle: dict[str, Any] | None = None
        if invoice.zelle_pending_submitted_at is not None:
            remaining = max(ZERO, money(principal) - money(confirmed))
            expires_at = _utc(invoice.zelle_pending_submitted_at) + timedelta(hours=24)
            linked_zelle = linked_zelle_attempts.get(invoice.id)
            if linked_zelle is not None and linked_zelle.source != "backfill":
                classification = "represented"
            elif linked_zelle is not None:
                classification = "active" if linked_zelle.state == "pending" else "expired"
                attempt_keys.append(linked_zelle.idempotency_key)
                event_keys.append(f"backfill:invoice:{invoice.id}:pending-zelle:event")
            elif remaining <= ZERO:
                classification = "superseded"
            elif expires_at <= cutoff_at:
                classification = "expired"
                attempt_keys.append(f"backfill:invoice:{invoice.id}:pending-zelle")
            else:
                classification = "active"
                attempt_keys.append(f"backfill:invoice:{invoice.id}:pending-zelle")
            if linked_zelle is None:
                event_keys.append(f"backfill:invoice:{invoice.id}:pending-zelle:event")
            zelle = {
                "classification": classification,
                "amount": remaining,
                "expires_at": expires_at,
                "linked_attempt": linked_zelle,
            }

        plan[invoice.id] = {
            "invoice": invoice,
            "principal": money(principal),
            "payments": payment_rows,
            "paid_snapshot_delta": paid_snapshot_delta,
            "unapplied_from_source": unapplied,
            "zelle": zelle,
            "attempt_keys": attempt_keys,
            "event_keys": event_keys,
            "existing_settlement": existing_settlement,
        }
    return plan


async def _baseline_result_envelope(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    invoice_ids: list[UUID],
) -> tuple[dict[str, int], dict[str, str], dict[str, set[str]]]:
    if not invoice_ids:
        empty_checksum = _checksum([])
        return (
            {"settlements": 0, "attempts": 0, "events": 0},
            {
                "result_settlements": empty_checksum,
                "result_attempts": empty_checksum,
                "result_events": empty_checksum,
            },
            {"settlements": set(), "attempts": set(), "events": set()},
        )

    settlements = (await db.execute(
        select(InvoiceSettlement).where(
            InvoiceSettlement.tenant_id == tenant_id,
            InvoiceSettlement.invoice_id.in_(invoice_ids),
            InvoiceSettlement.deleted_at.is_(None),
        )
    )).scalars().all()
    attempts = (await db.execute(
        select(InvoicePaymentAttempt).where(
            InvoicePaymentAttempt.tenant_id == tenant_id,
            InvoicePaymentAttempt.invoice_id.in_(invoice_ids),
            InvoicePaymentAttempt.source == "backfill",
            InvoicePaymentAttempt.deleted_at.is_(None),
        )
    )).scalars().all()
    events = (await db.execute(
        select(InvoicePaymentLedgerEvent).where(
            InvoicePaymentLedgerEvent.tenant_id == tenant_id,
            InvoicePaymentLedgerEvent.invoice_id.in_(invoice_ids),
            InvoicePaymentLedgerEvent.idempotency_key.like("backfill:%"),
        )
    )).scalars().all()

    baseline_totals: dict[UUID, dict[str, Any]] = {}
    for event in events:
        totals = baseline_totals.setdefault(event.settlement_id, {
            "confirmed": ZERO,
            "pending": ZERO,
            "unapplied": ZERO,
            "refund_pending": ZERO,
            "event_count": 0,
            "last_sequence": 0,
        })
        totals["confirmed"] = money(totals["confirmed"] + money(event.principal_delta))
        totals["pending"] = money(totals["pending"] + money(event.pending_delta))
        totals["unapplied"] = money(totals["unapplied"] + money(event.unapplied_delta))
        totals["refund_pending"] = money(
            totals["refund_pending"] + money(event.refund_pending_delta)
        )
        totals["event_count"] += 1
        totals["last_sequence"] = max(totals["last_sequence"], int(event.sequence or 0))

    settlement_rows = sorted(({
        "invoice_id": str(row.invoice_id),
        "customer_id": str(row.customer_id),
        "principal_total": str(money(row.principal_total)),
        "max_card_fee": str(money(row.max_card_fee)),
        "max_card_fee_tax": str(money(row.max_card_fee_tax)),
        "currency": row.currency,
        "baseline_confirmed_principal": str(money(
            baseline_totals.get(row.id, {}).get("confirmed", ZERO)
        )),
        "baseline_active_pending_principal": str(money(
            baseline_totals.get(row.id, {}).get("pending", ZERO)
        )),
        "baseline_unapplied_credit": str(money(
            baseline_totals.get(row.id, {}).get("unapplied", ZERO)
        )),
        "baseline_refund_pending": str(money(
            baseline_totals.get(row.id, {}).get("refund_pending", ZERO)
        )),
        "baseline_event_count": baseline_totals.get(row.id, {}).get("event_count", 0),
        "baseline_last_sequence": baseline_totals.get(row.id, {}).get("last_sequence", 0),
        "legacy_reconciliation_status": row.legacy_reconciliation_status,
        "legacy_reconciliation_note": row.legacy_reconciliation_note,
    } for row in settlements), key=lambda row: row["invoice_id"])
    attempt_rows = sorted(({
        "invoice_id": str(row.invoice_id),
        "payment_id": str(row.payment_id) if row.payment_id else None,
        "source": row.source,
        "rail": row.rail,
        "provider": row.provider,
        "principal_amount": str(money(row.principal_amount)),
        "provider_charge_amount": str(money(row.provider_charge_amount)),
        "state": row.state,
        "received_amount": str(money(row.received_amount)) if row.received_amount is not None else None,
        "applied_principal_amount": str(money(row.applied_principal_amount)),
        "unapplied_amount": str(money(row.unapplied_amount)),
        "applied_card_fee_amount": str(money(row.applied_card_fee_amount)),
        "applied_card_fee_tax_amount": str(money(row.applied_card_fee_tax_amount)),
        "processor_fee_amount": str(money(row.processor_fee_amount)),
        "provider_configuration_version": row.provider_configuration_version,
        "provider_account_id": row.provider_account_id,
        "expires_at": _timestamp(row.expires_at),
        "confirmed_at": _timestamp(row.confirmed_at),
        "failed_at": _timestamp(row.failed_at),
        "failure_code": row.failure_code,
        "version": row.version,
        "idempotency_key": row.idempotency_key,
    } for row in attempts), key=lambda row: row["idempotency_key"])
    event_rows = sorted(({
        "invoice_id": str(row.invoice_id),
        "attempt_id": str(row.attempt_id) if row.attempt_id else None,
        "idempotency_key": row.idempotency_key,
        "event_type": row.event_type,
        "principal_delta": str(money(row.principal_delta)),
        "pending_delta": str(money(row.pending_delta)),
        "unapplied_delta": str(money(row.unapplied_delta)),
        "refund_pending_delta": str(money(row.refund_pending_delta)),
        "evidence_snapshot": row.evidence_snapshot,
    } for row in events), key=lambda row: row["idempotency_key"])

    return (
        {"settlements": len(settlement_rows), "attempts": len(attempt_rows), "events": len(event_rows)},
        {
            "result_settlements": _checksum(settlement_rows),
            "result_attempts": _checksum(attempt_rows),
            "result_events": _checksum(event_rows),
        },
        {
            "settlements": {row["invoice_id"] for row in settlement_rows},
            "attempts": {row["idempotency_key"] for row in attempt_rows},
            "events": {row["idempotency_key"] for row in event_rows},
        },
    )


async def _fail_reconciliation(
    db: AsyncSession,
    run: InvoiceSettlementBackfillRun,
    message: str,
) -> None:
    run_id = run.id
    await db.rollback()
    persisted = await db.scalar(select(InvoiceSettlementBackfillRun).where(
        InvoiceSettlementBackfillRun.id == run_id,
    ).with_for_update())
    if persisted is None:
        raise ValueError(message)
    persisted.state = "failed"
    persisted.error_summary = message
    persisted.verified_at = None
    await db.commit()


async def _load_invoices_in_batches(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    cutoff_at: datetime,
    batch_size: int,
) -> list[Invoice]:
    rows: list[Invoice] = []
    cursor_created_at: datetime | None = None
    cursor_id: UUID | None = None
    while True:
        query = (
            select(Invoice)
            .options(selectinload(Invoice.repair_order).selectinload(RepairOrder.customer))
            .where(
                Invoice.tenant_id == tenant_id,
                Invoice.deleted_at.is_(None),
                Invoice.created_at <= cutoff_at,
            )
        )
        if cursor_created_at is not None and cursor_id is not None:
            query = query.where(or_(
                Invoice.created_at > cursor_created_at,
                and_(Invoice.created_at == cursor_created_at, Invoice.id > cursor_id),
            ))
        batch = (await db.execute(
            query.order_by(Invoice.created_at, Invoice.id).limit(batch_size)
        )).scalars().all()
        if not batch:
            return rows
        rows.extend(batch)
        cursor_created_at = _utc(batch[-1].created_at)
        cursor_id = batch[-1].id


async def _load_payments_in_batches(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    cutoff_at: datetime,
    batch_size: int,
) -> list[Payment]:
    rows: list[Payment] = []
    cursor_created_at: datetime | None = None
    cursor_id: UUID | None = None
    while True:
        query = select(Payment).where(
            Payment.tenant_id == tenant_id,
            Payment.deleted_at.is_(None),
            Payment.created_at <= cutoff_at,
            Payment.status.in_([PaymentStatus.COMPLETED, PaymentStatus.REFUNDED]),
        )
        if cursor_created_at is not None and cursor_id is not None:
            query = query.where(or_(
                Payment.created_at > cursor_created_at,
                and_(Payment.created_at == cursor_created_at, Payment.id > cursor_id),
            ))
        batch = (await db.execute(
            query.order_by(Payment.created_at, Payment.id).limit(batch_size)
        )).scalars().all()
        if not batch:
            return rows
        rows.extend(batch)
        cursor_created_at = _utc(batch[-1].created_at)
        cursor_id = batch[-1].id


async def _classify_existing_payment_links(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    invoices_by_id: dict[UUID, Invoice],
    payments: list[Payment],
    settlements_by_invoice: dict[UUID, InvoiceSettlement],
) -> tuple[dict[UUID, InvoicePaymentAttempt], str | None]:
    """Resolve exact reciprocal legacy-payment links before baseline mutation.

    A later cutoff sees both historical source rows and DB-048-native Payment
    compatibility projections.  Those projections are already represented and
    must be checksum-visible but never replayed as a second backfill attempt.
    """
    payment_ids = {payment.id for payment in payments}
    linked_attempt_ids = {
        payment.invoice_payment_attempt_id
        for payment in payments
        if payment.invoice_payment_attempt_id is not None
    }
    if not payment_ids and not linked_attempt_ids:
        return {}, None

    attempts = (await db.execute(select(InvoicePaymentAttempt).where(or_(
        InvoicePaymentAttempt.id.in_(linked_attempt_ids or {UUID(int=0)}),
        InvoicePaymentAttempt.payment_id.in_(payment_ids or {UUID(int=0)}),
    )))).scalars().all()
    attempts_by_id = {attempt.id: attempt for attempt in attempts}
    attempts_by_payment: dict[UUID, InvoicePaymentAttempt] = {}
    duplicate_payment_id: UUID | None = None
    for attempt in attempts:
        if attempt.payment_id is None:
            continue
        if attempt.payment_id in attempts_by_payment:
            duplicate_payment_id = attempt.payment_id
        attempts_by_payment[attempt.payment_id] = attempt

    linked_attempts: dict[UUID, InvoicePaymentAttempt] = {}
    for payment in payments:
        explicit = (
            attempts_by_id.get(payment.invoice_payment_attempt_id)
            if payment.invoice_payment_attempt_id is not None else None
        )
        reciprocal = attempts_by_payment.get(payment.id)
        if explicit is None and reciprocal is None:
            continue
        if duplicate_payment_id == payment.id or explicit is None or reciprocal is None or explicit.id != reciprocal.id:
            return {}, f"Payment {payment.id} has a non-reciprocal DB-048 attempt link"

        invoice = invoices_by_id.get(payment.invoice_id)
        settlement = settlements_by_invoice.get(payment.invoice_id)
        customer_id = (
            invoice.repair_order.customer_id
            if invoice is not None and invoice.repair_order is not None else None
        )
        rail, provider, provider_account = _legacy_rail(payment)
        if (
            invoice is None
            or settlement is None
            or explicit.deleted_at is not None
            or explicit.tenant_id != tenant_id
            or explicit.invoice_id != payment.invoice_id
            or explicit.settlement_id != settlement.id
            or explicit.customer_id != customer_id
            or explicit.payment_id != payment.id
            or payment.invoice_payment_attempt_id != explicit.id
            or rail is None
            or explicit.rail != rail
            or explicit.provider != provider
            or (provider_account is not None and explicit.provider_account_id != provider_account)
            or (
                money(explicit.applied_principal_amount) != money(payment.amount)
                and not (
                    explicit.source == "backfill"
                    and explicit.state in {"confirmed", "refunded"}
                    and money(explicit.received_amount) == money(payment.amount)
                    and money(
                        explicit.applied_principal_amount + explicit.unapplied_amount
                    ) == money(explicit.received_amount)
                )
            )
            or (
                payment.status == PaymentStatus.COMPLETED
                and explicit.state != "confirmed"
            )
            or (
                payment.status == PaymentStatus.REFUNDED
                and explicit.state not in {"refunded", "reversed"}
            )
        ):
            return {}, f"Payment {payment.id} DB-048 attempt identity or projection mismatch"
        linked_attempts[payment.id] = explicit

    if linked_attempts:
        linked_by_id = {attempt.id: attempt for attempt in linked_attempts.values()}
        linked_ids = set(linked_by_id)
        events = (await db.execute(select(InvoicePaymentLedgerEvent).where(
            InvoicePaymentLedgerEvent.tenant_id == tenant_id,
            InvoicePaymentLedgerEvent.attempt_id.in_(linked_ids),
        ))).scalars().all()
        evidenced: set[UUID] = set()
        for event in events:
            attempt = linked_by_id.get(event.attempt_id)
            if (
                attempt is not None
                and event.invoice_id == attempt.invoice_id
                and event.settlement_id == attempt.settlement_id
                and event.customer_id == attempt.customer_id
            ):
                evidenced.add(attempt.id)
        missing_evidence = linked_ids - evidenced
        if missing_evidence:
            return {}, f"DB-048 attempt {sorted(str(value) for value in missing_evidence)[0]} lacks ledger evidence"

    native_invoice_ids = {
        attempt.invoice_id for attempt in linked_attempts.values() if attempt.source != "backfill"
    }
    for invoice_id in native_invoice_ids:
        unlinked = [
            payment for payment in payments
            if payment.invoice_id == invoice_id and payment.id not in linked_attempts
        ]
        if unlinked:
            return {}, f"Invoice {invoice_id} mixes native DB-048 activity with unlinked legacy payment sources"

    for payment in payments:
        settlement = settlements_by_invoice.get(payment.invoice_id)
        if (
            payment.id not in linked_attempts
            and settlement is not None
            and settlement.legacy_reconciliation_status == "legacy_paid_without_tender"
        ):
            return {}, (
                f"Invoice {payment.invoice_id} has an unattributed paid baseline "
                "and a later unlinked payment source"
            )

    return linked_attempts, None


async def _classify_current_zelle_links(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    invoices: list[Invoice],
    settlements_by_invoice: dict[UUID, InvoiceSettlement],
) -> tuple[dict[UUID, InvoicePaymentAttempt], str | None]:
    pending_invoices = [
        invoice for invoice in invoices if invoice.zelle_pending_submitted_at is not None
    ]
    if not pending_invoices:
        return {}, None
    invoice_ids = {invoice.id for invoice in pending_invoices}
    attempts = (await db.execute(select(InvoicePaymentAttempt).where(
        InvoicePaymentAttempt.tenant_id == tenant_id,
        InvoicePaymentAttempt.invoice_id.in_(invoice_ids),
        InvoicePaymentAttempt.rail == "zelle",
        InvoicePaymentAttempt.deleted_at.is_(None),
    ))).scalars().all()
    by_invoice: dict[UUID, list[InvoicePaymentAttempt]] = {}
    for attempt in attempts:
        by_invoice.setdefault(attempt.invoice_id, []).append(attempt)

    linked: dict[UUID, InvoicePaymentAttempt] = {}
    for invoice in pending_invoices:
        settlement = settlements_by_invoice.get(invoice.id)
        candidates = sorted(
            (
                attempt for attempt in by_invoice.get(invoice.id, [])
                if settlement is not None
                and current_zelle_attempt_matches(
                    invoice=invoice,
                    settlement=settlement,
                    attempt=attempt,
                )
            ),
            key=lambda attempt: (_utc(attempt.created_at), attempt.id),
            reverse=True,
        )
        if not candidates:
            if by_invoice.get(invoice.id):
                return {}, f"Invoice {invoice.id} pending Zelle source does not match its DB-048 attempt"
            continue
        attempt = candidates[0]
        customer_id = invoice.repair_order.customer_id if invoice.repair_order else None
        if (
            settlement is None
            or attempt.settlement_id != settlement.id
            or attempt.customer_id != customer_id
            or attempt.invoice_id != invoice.id
            or attempt.tenant_id != tenant_id
        ):
            return {}, f"Invoice {invoice.id} pending Zelle attempt identity mismatch"
        event = await db.scalar(select(InvoicePaymentLedgerEvent.id).where(
            InvoicePaymentLedgerEvent.tenant_id == tenant_id,
            InvoicePaymentLedgerEvent.invoice_id == invoice.id,
            InvoicePaymentLedgerEvent.settlement_id == settlement.id,
            InvoicePaymentLedgerEvent.attempt_id == attempt.id,
            InvoicePaymentLedgerEvent.customer_id == customer_id,
        ).limit(1))
        if event is None:
            return {}, f"Invoice {invoice.id} pending Zelle attempt lacks ledger evidence"
        linked[invoice.id] = attempt
    return linked, None


async def backfill_tenant_invoice_settlements(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    cutoff_at: datetime,
    batch_size: int = DEFAULT_BACKFILL_BATCH_SIZE,
) -> InvoiceSettlementBackfillRun:
    """Create or re-verify factual baselines without inventing tender details."""
    cutoff_at = _utc(cutoff_at)
    if batch_size < 1 or batch_size > 1000:
        raise ValueError("batch_size must be between 1 and 1000")
    existing_run = await db.scalar(select(InvoiceSettlementBackfillRun).where(
        InvoiceSettlementBackfillRun.tenant_id == tenant_id,
        InvoiceSettlementBackfillRun.cutoff_at == cutoff_at,
    ))
    tenant = await db.get(Tenant, tenant_id)
    config = await db.scalar(select(TenantPaymentProviderConfiguration).where(
        TenantPaymentProviderConfiguration.tenant_id == tenant_id,
        TenantPaymentProviderConfiguration.is_active.is_(True),
        TenantPaymentProviderConfiguration.deleted_at.is_(None),
    ))
    if not tenant or not config:
        raise ValueError("Tenant and active DB-048 provider configuration are required before backfill")

    run = existing_run or InvoiceSettlementBackfillRun(
        tenant_id=tenant_id,
        cutoff_at=cutoff_at,
        state="running",
        source_counts={},
        inserted_counts={},
        source_checksums={},
    )
    if existing_run is None:
        db.add(run)
        await db.flush()

    invoices = await _load_invoices_in_batches(
        db, tenant_id=tenant_id, cutoff_at=cutoff_at, batch_size=batch_size,
    )
    source_payments = await _load_payments_in_batches(
        db, tenant_id=tenant_id, cutoff_at=cutoff_at, batch_size=batch_size,
    )

    eligibility = {invoice.id: _invoice_eligibility(invoice) for invoice in invoices}
    eligible_invoices = [invoice for invoice in invoices if eligibility[invoice.id][0]]
    eligible_ids = {invoice.id for invoice in eligible_invoices}
    invoice_rows = [
        _invoice_source_row(
            invoice,
            eligible=eligibility[invoice.id][0],
            ineligible_reason=eligibility[invoice.id][1],
        )
        for invoice in invoices
    ]
    payment_rows: list[dict[str, Any]] = []
    payments_by_invoice: dict[UUID, list[Payment]] = {}
    eligible_source_payments: list[Payment] = []
    for payment in source_payments:
        is_eligible = payment.invoice_id in eligible_ids
        payment_rows.append(_payment_source_row(
            payment,
            eligible=is_eligible,
            ineligible_reason=None if is_eligible else "invoice_not_eligible",
        ))
        if is_eligible:
            eligible_source_payments.append(payment)
            payments_by_invoice.setdefault(payment.invoice_id, []).append(payment)

    pending_rows = [
        _pending_zelle_source_row(
            invoice,
            eligible=eligibility[invoice.id][0],
            ineligible_reason=eligibility[invoice.id][1],
        )
        for invoice in invoices
        if invoice.zelle_pending_submitted_at is not None
    ]
    has_frozen_source_envelope = bool(existing_run) and all(
        key in (existing_run.source_checksums or {}) for key in _SOURCE_CHECKSUM_KEYS
    )
    existing_settlements = (await db.execute(select(InvoiceSettlement).where(
        InvoiceSettlement.tenant_id == tenant_id,
        InvoiceSettlement.invoice_id.in_(eligible_ids or {UUID(int=0)}),
        InvoiceSettlement.deleted_at.is_(None),
    ))).scalars().all()
    settlements_by_invoice = {settlement.invoice_id: settlement for settlement in existing_settlements}
    linked_attempts, linkage_error = await _classify_existing_payment_links(
        db,
        tenant_id=tenant_id,
        invoices_by_id={invoice.id: invoice for invoice in eligible_invoices},
        payments=eligible_source_payments,
        settlements_by_invoice=settlements_by_invoice,
    )
    if linkage_error:
        await db.rollback()
        raise ValueError(linkage_error)
    linked_zelle_attempts, zelle_linkage_error = await _classify_current_zelle_links(
        db,
        tenant_id=tenant_id,
        invoices=eligible_invoices,
        settlements_by_invoice=settlements_by_invoice,
    )
    if zelle_linkage_error:
        await db.rollback()
        raise ValueError(zelle_linkage_error)

    # A verified baseline owns legacy rows and prior backfill projections. A
    # later native DB-048 attempt is an immutable, mutually linked projection,
    # not a new legacy source to replay. Excluding only those exact native rows
    # keeps safe reruns stable while any unlinked or mismatched source still
    # fails the preflight classifiers or the checksum comparison.
    baseline_payment_rows = [
        row for row, payment in zip(payment_rows, source_payments)
        if (
            payment.invoice_id not in eligible_ids
            or payment.id not in linked_attempts
            or linked_attempts[payment.id].source == "backfill"
        )
    ]
    linked_zelle_by_invoice = {
        invoice_id: attempt
        for invoice_id, attempt in linked_zelle_attempts.items()
    }
    baseline_pending_rows = [
        row for row in pending_rows
        if (
            UUID(row["invoice_id"]) not in linked_zelle_by_invoice
            or linked_zelle_by_invoice[UUID(row["invoice_id"])].source == "backfill"
        )
    ]
    source_checksums = {
        "invoices": _checksum(invoice_rows),
        "payments": _checksum(baseline_payment_rows),
        "pending_zelle": _checksum(baseline_pending_rows),
    }
    if existing_run and has_frozen_source_envelope:
        prior_checksums = dict(existing_run.source_checksums or {})
        drifted_sources = [
            key for key in _SOURCE_CHECKSUM_KEYS if prior_checksums.get(key) != source_checksums[key]
        ]
        if drifted_sources:
            message = f"Source checksum drift: {', '.join(sorted(drifted_sources))}"
            await _fail_reconciliation(db, run, message)
            raise ValueError(message)
    plan = _baseline_plan(
        invoices=eligible_invoices,
        payments_by_invoice=payments_by_invoice,
        linked_attempts=linked_attempts,
        linked_zelle_attempts=linked_zelle_attempts,
        settlements_by_invoice=settlements_by_invoice,
        cutoff_at=cutoff_at,
    )

    reason_counts = Counter(reason for ok, reason in eligibility.values() if not ok and reason)
    source_counts: dict[str, Any] = {
        "invoices": len(invoices),
        "payments": len(source_payments),
        "pending_zelle": len(pending_rows),
        "invoices_total": len(invoices),
        "invoices_eligible": len(eligible_invoices),
        "invoices_ineligible": len(invoices) - len(eligible_invoices),
        "ineligible_invoice_reasons": dict(sorted(reason_counts.items())),
        "payments_total": len(source_payments),
        "payments_eligible": sum(row["eligible"] for row in payment_rows),
        "payments_ineligible": sum(not row["eligible"] for row in payment_rows),
        "payments_supported": sum(
            row["eligible"] and row["rail"] is not None and money(row["amount"]) > ZERO
            for row in payment_rows
        ),
        "payments_unsupported": sum(
            row["eligible"] and row["rail"] is None and money(row["amount"]) > ZERO
            for row in payment_rows
        ),
        "payments_nonpositive": sum(
            row["eligible"] and money(row["amount"]) <= ZERO for row in payment_rows
        ),
        "payments_already_linked": len(linked_attempts),
        "pending_zelle_already_linked": len(linked_zelle_attempts),
        "pending_zelle_total": len(pending_rows),
        "pending_zelle_eligible": sum(row["eligible"] for row in pending_rows),
        "pending_zelle_ineligible": sum(not row["eligible"] for row in pending_rows),
        "pending_zelle_active": sum(
            item["zelle"] is not None and item["zelle"]["classification"] == "active"
            for item in plan.values()
        ),
        "pending_zelle_expired": sum(
            item["zelle"] is not None and item["zelle"]["classification"] == "expired"
            for item in plan.values()
        ),
        "pending_zelle_superseded": sum(
            item["zelle"] is not None and item["zelle"]["classification"] == "superseded"
            for item in plan.values()
        ),
    }

    expected_keys = {
        "settlements": {str(invoice.id) for invoice in eligible_invoices},
        "attempts": {key for item in plan.values() for key in item["attempt_keys"]},
        "events": {key for item in plan.values() for key in item["event_keys"]},
    }

    if existing_run and has_frozen_source_envelope:
        prior_checksums = dict(existing_run.source_checksums or {})
        if existing_run.state != "running":
            result_counts, result_checksums, result_keys = await _baseline_result_envelope(
                db,
                tenant_id=tenant_id,
                invoice_ids=[invoice.id for invoice in eligible_invoices],
            )
            drifted_results = [
                name for name in ("settlements", "attempts", "events")
                if result_keys[name] != expected_keys[name]
                or int((existing_run.inserted_counts or {}).get(name, -1)) != result_counts[name]
                or prior_checksums.get(f"result_{name}") != result_checksums[f"result_{name}"]
            ]
            if drifted_results:
                message = (
                    "Baseline result count/checksum drift: "
                    f"{', '.join(sorted(drifted_results))}"
                )
                await _fail_reconciliation(db, run, message)
                raise ValueError(message)

            run.source_counts = source_counts
            run.state = "verified"
            run.error_summary = None
            run.verified_at = datetime.now(timezone.utc)
            await db.flush()
            return run

    run.state = "running"
    run.error_summary = None
    if not has_frozen_source_envelope:
        run.source_counts = source_counts
        run.source_checksums = dict(source_checksums)
        run.batch_cursor = "0"
        await db.commit()
    start_index = int(run.batch_cursor or "0")

    for invoice_index, invoice in enumerate(eligible_invoices):
        if invoice_index < start_index:
            continue
        item = plan[invoice.id]
        customer_id = invoice.repair_order.customer_id
        settlement = await db.scalar(select(InvoiceSettlement).where(
            InvoiceSettlement.tenant_id == tenant_id,
            InvoiceSettlement.invoice_id == invoice.id,
            InvoiceSettlement.deleted_at.is_(None),
        ))
        if settlement is None:
            principal, fee, fee_tax, tax_rate, fee_rate = invoice_money_snapshot(invoice)
            settlement = InvoiceSettlement(
                tenant_id=tenant_id,
                invoice_id=invoice.id,
                customer_id=customer_id,
                principal_total=principal,
                max_card_fee=fee,
                max_card_fee_tax=fee_tax,
                sales_tax_rate_snapshot=tax_rate,
                card_fee_rate_snapshot=fee_rate,
                confirmed_principal=ZERO,
                active_pending_principal=ZERO,
                state="unpaid",
                accounting_sync_status="not_required",
                legacy_reconciliation_status="backfill_running",
            )
            db.add(settlement)
            await db.flush()
        else:
            existing_backfill_event = await db.scalar(select(InvoicePaymentLedgerEvent.id).where(
                InvoicePaymentLedgerEvent.tenant_id == tenant_id,
                InvoicePaymentLedgerEvent.settlement_id == settlement.id,
                InvoicePaymentLedgerEvent.idempotency_key.like("backfill:%"),
            ).limit(1))
            has_unattributed_projection = any((
                money(settlement.confirmed_principal) > ZERO,
                money(settlement.active_pending_principal) > ZERO,
                money(settlement.unapplied_credit) > ZERO,
                money(settlement.refund_pending) > ZERO,
                int(settlement.last_event_sequence or 0) > 0,
            ))
            if (
                existing_backfill_event is None
                and has_unattributed_projection
                and not any(
                    payment_item["linked_attempt"] is not None
                    for payment_item in item["payments"]
                )
            ):
                message = (
                    f"Invoice {invoice.id} already has a financial settlement projection "
                    "that cannot be attributed to this backfill"
                )
                await _fail_reconciliation(db, run, message)
                raise ValueError(message)

        for payment_item in item["payments"]:
            payment = payment_item["payment"]
            if payment_item["linked_attempt"] is not None:
                continue
            event_key = f"backfill:payment:{payment.id}:event"
            existing_event = await db.scalar(select(InvoicePaymentLedgerEvent).where(
                InvoicePaymentLedgerEvent.tenant_id == tenant_id,
                InvoicePaymentLedgerEvent.idempotency_key == event_key,
            ))
            if existing_event is not None:
                continue

            received: Decimal = payment_item["received"]
            refunded: bool = payment_item["refunded"]
            valid_amount: bool = payment_item["valid_amount"]
            applied: Decimal = payment_item["applied"]
            excess: Decimal = payment_item["excess"]
            rail, provider, provider_account = _legacy_rail(payment)
            attempt = None
            if valid_amount and rail:
                attempt_key = f"backfill:payment:{payment.id}"
                attempt = await db.scalar(select(InvoicePaymentAttempt).where(
                    InvoicePaymentAttempt.tenant_id == tenant_id,
                    InvoicePaymentAttempt.idempotency_key == attempt_key,
                    InvoicePaymentAttempt.deleted_at.is_(None),
                ))
                if attempt is None:
                    if config.qbo_realm_snapshot:
                        await bind_settlement_accounting_realm(
                            db, settlement=settlement, config=config,
                        )
                        # Freeze the invoice/accounting realm before the
                        # backfilled attempt is inserted. The immutable realm
                        # guard intentionally rejects dialect-dependent
                        # same-flush ordering once an attempt is visible.
                        await db.flush([settlement])
                    attempt = InvoicePaymentAttempt(
                        tenant_id=tenant_id,
                        invoice_id=invoice.id,
                        settlement_id=settlement.id,
                        customer_id=customer_id,
                        payment_id=payment.id,
                        source="backfill",
                        rail=rail,
                        provider=provider,
                        state="refunded" if refunded else "confirmed",
                        principal_amount=received,
                        card_fee_amount=ZERO,
                        card_fee_tax_amount=ZERO,
                        provider_charge_amount=received,
                        received_amount=received,
                        applied_principal_amount=applied,
                        unapplied_amount=excess,
                        processor_fee_amount=ZERO,
                        currency="USD",
                        provider_configuration_version=config.version,
                        provider_account_id=(
                            provider_account
                            or (config.provider_account_snapshot if provider == config.selected_provider else None)
                        ),
                        provider_intent_id=payment.stripe_payment_intent_id,
                        provider_charge_id=payment.stripe_charge_id or payment.quickbooks_charge_id,
                        provider_reference=payment.reference_number,
                        manual_evidence={"origin": "legacy_payment", "details_reconstructed": False},
                        actor_user_id=payment.recorded_by_user_id,
                        actor_name_snapshot="Legacy payment",
                        actor_role_snapshot=None,
                        subject_type="backfill",
                        subject_id=None,
                        idempotency_key=attempt_key,
                        request_hash=_checksum([{
                            "payment_id": str(payment.id),
                            "amount": str(received),
                            "method": _enum_value(payment.method),
                            "status": _enum_value(payment.status),
                        }]),
                        version=1,
                        confirmed_at=payment.created_at,
                    )
                    db.add(attempt)
                    await db.flush()
                if payment.invoice_payment_attempt_id not in (None, attempt.id):
                    message = f"Legacy payment {payment.id} is linked to a different attempt"
                    await _fail_reconciliation(db, run, message)
                    raise ValueError(message)
                payment.invoice_payment_attempt_id = attempt.id

            if valid_amount:
                settlement.confirmed_principal = money(settlement.confirmed_principal) + applied
                settlement.unapplied_credit = money(settlement.unapplied_credit) + excess
            event_type = (
                "legacy_invalid_payment_baseline"
                if not valid_amount
                else ("legacy_refund_baseline" if refunded else "legacy_payment_baseline")
            )
            await append_ledger_event(
                db,
                settlement=settlement,
                attempt=attempt,
                event_type=event_type,
                idempotency_key=event_key,
                actor=None,
                principal_delta=applied,
                unapplied_delta=excess,
                evidence={
                    "origin": "baseline",
                    "payment_id": str(payment.id),
                    "legacy_method": _enum_value(payment.method),
                    "details_reconstructed": False,
                    "invalid_nonpositive_amount": not valid_amount,
                },
            )

        paid_snapshot_delta: Decimal = item["paid_snapshot_delta"]
        if paid_snapshot_delta > ZERO:
            paid_key = f"backfill:invoice:{invoice.id}:paid-baseline"
            existing_paid_event = await db.scalar(select(InvoicePaymentLedgerEvent).where(
                InvoicePaymentLedgerEvent.tenant_id == tenant_id,
                InvoicePaymentLedgerEvent.idempotency_key == paid_key,
            ))
            if existing_paid_event is None:
                settlement.confirmed_principal = money(settlement.confirmed_principal) + paid_snapshot_delta
                await append_ledger_event(
                    db,
                    settlement=settlement,
                    event_type="legacy_paid_snapshot",
                    idempotency_key=paid_key,
                    actor=None,
                    principal_delta=paid_snapshot_delta,
                    evidence={
                        "origin": "baseline",
                        "reconstructed_tender": False,
                        "unattributed_principal": str(paid_snapshot_delta),
                    },
                )

        zelle = item["zelle"]
        if zelle is not None:
            if zelle["linked_attempt"] is not None:
                # The current compatibility source is already represented by
                # an exact native or prior-backfill attempt. Preserve its
                # projection byte-for-byte across cutoff advancement.
                pass
            elif zelle["classification"] == "represented":
                pass
            else:
                event_key = f"backfill:invoice:{invoice.id}:pending-zelle:event"
                existing_zelle_event = await db.scalar(select(InvoicePaymentLedgerEvent).where(
                    InvoicePaymentLedgerEvent.tenant_id == tenant_id,
                    InvoicePaymentLedgerEvent.idempotency_key == event_key,
                ))
                if existing_zelle_event is None:
                    attempt = None
                    classification = zelle["classification"]
                    amount = money(zelle["amount"])
                    if classification in {"active", "expired"}:
                        attempt_key = f"backfill:invoice:{invoice.id}:pending-zelle"
                        attempt = await db.scalar(select(InvoicePaymentAttempt).where(
                            InvoicePaymentAttempt.tenant_id == tenant_id,
                            InvoicePaymentAttempt.idempotency_key == attempt_key,
                            InvoicePaymentAttempt.deleted_at.is_(None),
                        ))
                        if attempt is None:
                            if config.qbo_realm_snapshot:
                                await bind_settlement_accounting_realm(
                                    db, settlement=settlement, config=config,
                                )
                                await db.flush([settlement])
                            attempt = InvoicePaymentAttempt(
                                tenant_id=tenant_id,
                                invoice_id=invoice.id,
                                settlement_id=settlement.id,
                                customer_id=customer_id,
                                source="backfill",
                                rail="zelle",
                                provider="manual",
                                state="pending" if classification == "active" else "expired",
                                principal_amount=amount,
                                provider_charge_amount=amount,
                                provider_configuration_version=config.version,
                                manual_evidence={
                                    "origin": "legacy_pending_zelle",
                                    "compatibility_submitted_at": _timestamp(
                                        invoice.zelle_pending_submitted_at
                                    ),
                                    "sender_email_present": bool(invoice.zelle_pending_sender_email),
                                    "sender_phone_present": bool(invoice.zelle_pending_sender_phone),
                                },
                                actor_name_snapshot="Legacy Zelle submission",
                                subject_type="backfill",
                                idempotency_key=attempt_key,
                                request_hash=_checksum([{
                                    "invoice_id": str(invoice.id),
                                    "amount": str(amount),
                                    "submitted_at": _timestamp(invoice.zelle_pending_submitted_at),
                                }]),
                                expires_at=zelle["expires_at"],
                                failed_at=cutoff_at if classification == "expired" else None,
                                failure_code="legacy_zelle_expired" if classification == "expired" else None,
                            )
                            db.add(attempt)
                            await db.flush()
                        if classification == "active":
                            settlement.active_pending_principal = money(
                                settlement.active_pending_principal
                            ) + amount

                    event_type = {
                        "active": "legacy_zelle_pending_baseline",
                        "expired": "legacy_zelle_expired_baseline",
                        "superseded": "legacy_zelle_superseded_baseline",
                    }[classification]
                    await append_ledger_event(
                        db,
                        settlement=settlement,
                        attempt=attempt,
                        event_type=event_type,
                        idempotency_key=event_key,
                        actor=None,
                        pending_delta=amount if classification == "active" else ZERO,
                        evidence={
                            "origin": "baseline",
                            "receipt_confirmed": False,
                            "classification": classification,
                        },
                    )

        if item["existing_settlement"] is None:
            settlement.legacy_reconciliation_status = (
                "legacy_overage_review_required"
                if money(item["unapplied_from_source"]) > ZERO
                else (
                    "legacy_paid_without_tender"
                    if money(item["paid_snapshot_delta"]) > ZERO
                    else "reconciled"
                )
            )
            settlement.legacy_reconciliation_note = (
                "Historical overage retained for staff reconciliation; no automatic refund was initiated."
                if money(item["unapplied_from_source"]) > ZERO
                else None
            )
        settlement.state = settlement_state(settlement)
        processed = invoice_index + 1
        if processed % batch_size == 0:
            run.batch_cursor = str(processed)
            await db.commit()

    await db.flush()
    result_counts, result_checksums, result_keys = await _baseline_result_envelope(
        db,
        tenant_id=tenant_id,
        invoice_ids=[invoice.id for invoice in eligible_invoices],
    )
    mismatches = [
        name for name in ("settlements", "attempts", "events")
        if result_keys[name] != expected_keys[name]
    ]
    if mismatches:
        message = f"Source/result reconciliation failed: {', '.join(sorted(mismatches))}"
        await _fail_reconciliation(db, run, message)
        raise ValueError(message)

    run.source_counts = source_counts
    run.inserted_counts = result_counts
    run.source_checksums = {**source_checksums, **result_checksums}
    run.state = "reconciled"
    run.reconciled_at = datetime.now(timezone.utc)
    run.state = "verified"
    run.batch_cursor = None
    run.verified_at = datetime.now(timezone.utc)
    run.error_summary = None
    await db.flush()
    return run
