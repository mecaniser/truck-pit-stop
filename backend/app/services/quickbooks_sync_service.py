"""Durable QuickBooks invoice sync and payment reconciliation workers."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.db.models.customer import Customer
from app.db.models.invoice import Invoice
from app.db.models.payment import Payment, PaymentMethod, PaymentStatus
from app.db.models.provider_outbox import ProviderOutboxEvent, ProviderOutboxStatus
from app.db.models.quickbooks_connection import QuickBooksConnection
from app.db.models.repair_order import RepairOrder
from app.db.session import AsyncSessionLocal
from app.services.quickbooks_accounting_service import (
    QuickBooksAccountingError,
    change_data_capture,
    create_refund_receipt,
    sync_invoice,
    sync_payment,
)
from app.services.quickbooks_payments_service import QuickBooksPaymentError, get_charge, is_successful_charge
from app.services.quickbooks_service import QuickBooksOAuthError, refresh_access_token, save_token_set


QUICKBOOKS_INVOICE_SYNC_EVENT = "quickbooks.invoice.sync.v1"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _quickbooks_sync_lease_seconds() -> int:
    """Cover the bounded worst-case QBO request sequence for one invoice.

    A sync can refresh a token and then perform customer, item/account, and
    invoice lookup/create calls.  Every request has the configured HTTP
    timeout, so twelve timeout windows plus a minute of local overhead keeps a
    second worker from reclaiming a provider call that is still in flight.
    """
    return max(
        settings.PROVIDER_OUTBOX_LEASE_SECONDS,
        int(settings.QUICKBOOKS_HTTP_TIMEOUT_SECONDS * 12) + 60,
    )


async def enqueue_quickbooks_invoice_sync(
    db: AsyncSession,
    *,
    invoice: Invoice,
    operation: str = "sync",
) -> ProviderOutboxEvent:
    event = ProviderOutboxEvent(
        tenant_id=invoice.tenant_id,
        event_type=QUICKBOOKS_INVOICE_SYNC_EVENT,
        aggregate_type="quickbooks_invoice",
        aggregate_id=invoice.id,
        payload={"invoice_id": str(invoice.id), "operation": operation},
        idempotency_key=f"quickbooks-invoice:{invoice.id}:{operation}:v1",
        status=ProviderOutboxStatus.PENDING.value,
        available_at=_now(),
    )
    try:
        # The deterministic key is the final authority.  A savepoint keeps a
        # concurrent enqueue from aborting the caller's surrounding invoice or
        # OAuth transaction when PostgreSQL reports the unique-key conflict.
        async with db.begin_nested():
            db.add(event)
            await db.flush()
    except IntegrityError:
        existing = (await db.execute(
            select(ProviderOutboxEvent).where(
                ProviderOutboxEvent.tenant_id == invoice.tenant_id,
                ProviderOutboxEvent.event_type == QUICKBOOKS_INVOICE_SYNC_EVENT,
                ProviderOutboxEvent.idempotency_key == event.idempotency_key,
            )
        )).scalar_one_or_none()
        if existing is None:
            raise
        return existing
    return event


async def _refresh_if_needed(connection: QuickBooksConnection) -> None:
    expires = connection.access_token_expires_at
    if not expires or expires > _now() + timedelta(minutes=5):
        return
    token_set = await refresh_access_token(connection)
    save_token_set(connection, realm_id=connection.realm_id or "", token_set=token_set)
    connection.last_token_refresh_at = _now()
    connection.last_token_refresh_error = None


async def _quickbooks_claim_is_current(
    db: AsyncSession,
    *,
    event_id: UUID,
    lock_token: str,
) -> bool:
    """Check lease ownership without flushing provider-side ORM changes."""
    with db.no_autoflush:
        current = (await db.execute(
            select(ProviderOutboxEvent.id).where(
                ProviderOutboxEvent.id == event_id,
                ProviderOutboxEvent.status
                == ProviderOutboxStatus.PROCESSING.value,
                ProviderOutboxEvent.lock_token == lock_token,
            )
        )).scalar_one_or_none()
    return current is not None


async def _claim_next_quickbooks_sync_event(
    db: AsyncSession,
) -> tuple[UUID, str] | None:
    """Lease one event immediately before processing it."""
    claim_now = _now()
    event = (await db.execute(
        select(ProviderOutboxEvent)
        .where(
            ProviderOutboxEvent.event_type == QUICKBOOKS_INVOICE_SYNC_EVENT,
            or_(
                (
                    ProviderOutboxEvent.status
                    == ProviderOutboxStatus.PENDING.value
                )
                & (ProviderOutboxEvent.available_at <= claim_now),
                (
                    ProviderOutboxEvent.status
                    == ProviderOutboxStatus.PROCESSING.value
                )
                & ProviderOutboxEvent.locked_until.is_not(None)
                & (ProviderOutboxEvent.locked_until <= claim_now),
            ),
        )
        .order_by(
            ProviderOutboxEvent.available_at,
            ProviderOutboxEvent.created_at,
        )
        .limit(1)
        .with_for_update(skip_locked=True)
    )).scalar_one_or_none()
    if event is None:
        await db.rollback()
        return None
    token = uuid4().hex
    event.status = ProviderOutboxStatus.PROCESSING.value
    event.attempt_count += 1
    event.locked_at = claim_now
    event.locked_until = claim_now + timedelta(
        seconds=_quickbooks_sync_lease_seconds()
    )
    event.lock_token = token
    event.last_attempt_at = claim_now
    await db.commit()
    return event.id, token


async def process_quickbooks_invoice_sync_events(
    *,
    session_factory: async_sessionmaker[AsyncSession] = AsyncSessionLocal,
    batch_size: int = 20,
) -> dict[str, int]:
    results = {"processed": 0, "succeeded": 0, "retried": 0, "dead": 0, "skipped": 0}
    for _ in range(batch_size):
        async with session_factory() as db:
            claim = await _claim_next_quickbooks_sync_event(db)
        if claim is None:
            break
        event_id, lock_token = claim
        results["processed"] += 1
        async with session_factory() as db:
            event = await db.get(ProviderOutboxEvent, event_id)
            if (
                not event
                or event.status != ProviderOutboxStatus.PROCESSING.value
                or event.lock_token != lock_token
            ):
                results["skipped"] += 1
                continue
            invoice = (await db.execute(
                select(Invoice)
                .options(
                    selectinload(Invoice.tenant),
                    selectinload(Invoice.repair_order).selectinload(RepairOrder.customer),
                )
                .where(
                    Invoice.id == event.aggregate_id,
                    Invoice.tenant_id == event.tenant_id,
                    Invoice.repair_order.has(
                        (RepairOrder.tenant_id == event.tenant_id)
                        & RepairOrder.customer.has(
                            Customer.tenant_id == event.tenant_id
                        )
                    ),
                )
            )).scalar_one_or_none()
            connection = (await db.execute(
                select(QuickBooksConnection).where(
                    QuickBooksConnection.tenant_id == event.tenant_id,
                    QuickBooksConnection.status == "connected",
                )
            )).scalar_one_or_none()
            if not invoice or not invoice.repair_order or not invoice.repair_order.customer:
                event.status = ProviderOutboxStatus.DEAD.value
                event.last_error = "Invoice accounting context is unavailable"
                event.completed_at = _now()
                event.locked_until = None
                event.lock_token = None
                results["dead"] += 1
                await db.commit()
                continue
            if not connection:
                # A garage can finalize invoices before choosing QuickBooks.
                # Keep the event retryable so connecting later backfills them.
                event.status = ProviderOutboxStatus.PENDING.value
                event.available_at = _now() + timedelta(hours=6)
                event.last_error = "QuickBooks is not connected"
                event.locked_until = None
                event.lock_token = None
                results["retried"] += 1
                await db.commit()
                continue
            try:
                await _refresh_if_needed(connection)
                await sync_invoice(connection, invoice, invoice.repair_order.customer)
                if not await _quickbooks_claim_is_current(
                    db,
                    event_id=event_id,
                    lock_token=lock_token,
                ):
                    await db.rollback()
                    results["skipped"] += 1
                    continue
                event.status = ProviderOutboxStatus.SUCCEEDED.value
                event.completed_at = _now()
                event.last_error = None
                event.locked_until = None
                event.lock_token = None
                results["succeeded"] += 1
            except (QuickBooksAccountingError, QuickBooksOAuthError) as exc:
                if not await _quickbooks_claim_is_current(
                    db,
                    event_id=event_id,
                    lock_token=lock_token,
                ):
                    await db.rollback()
                    results["skipped"] += 1
                    continue
                invoice.quickbooks_sync_status = "error"
                invoice.quickbooks_sync_error = str(exc)
                event.last_error = f"{type(exc).__name__}: {str(exc)[:500]}"
                if event.attempt_count >= settings.PROVIDER_OUTBOX_MAX_ATTEMPTS:
                    event.status = ProviderOutboxStatus.DEAD.value
                    event.completed_at = _now()
                    event.locked_until = None
                    event.lock_token = None
                    results["dead"] += 1
                else:
                    event.status = ProviderOutboxStatus.PENDING.value
                    event.available_at = _now() + timedelta(minutes=min(60, 2 ** event.attempt_count))
                    event.locked_until = None
                    event.lock_token = None
                    results["retried"] += 1
            await db.commit()
    return results


async def reconcile_quickbooks_payments(
    *,
    session_factory: async_sessionmaker[AsyncSession] = AsyncSessionLocal,
    limit: int = 100,
) -> dict[str, int]:
    results = {"checked": 0, "reconciled": 0, "failed": 0}
    cutoff = _now() - timedelta(hours=12)
    async with session_factory() as db:
        payments = (await db.execute(
            select(Payment)
            .options(
                selectinload(Payment.invoice).selectinload(Invoice.tenant),
                selectinload(Payment.invoice)
                .selectinload(Invoice.repair_order)
                .selectinload(RepairOrder.customer)
            )
            .where(
                Payment.method == PaymentMethod.QUICKBOOKS,
                Payment.quickbooks_charge_id.is_not(None),
                Payment.status.in_([PaymentStatus.PENDING, PaymentStatus.COMPLETED]),
                or_(
                    Payment.quickbooks_reconciled_at.is_(None),
                    Payment.quickbooks_reconciled_at <= cutoff,
                ),
            )
            .limit(limit)
        )).scalars().all()
        for payment in payments:
            results["checked"] += 1
            connection = (await db.execute(
                select(QuickBooksConnection).where(
                    QuickBooksConnection.tenant_id == payment.tenant_id,
                    QuickBooksConnection.status == "connected",
                )
            )).scalar_one_or_none()
            customer = payment.invoice.repair_order.customer if payment.invoice and payment.invoice.repair_order else None
            if not connection or not customer:
                payment.quickbooks_sync_error = "QuickBooks reconciliation context is unavailable"
                results["failed"] += 1
                continue
            try:
                await _refresh_if_needed(connection)
                charge = await get_charge(connection=connection, charge_id=payment.quickbooks_charge_id or "")
                payment.quickbooks_charge_status = charge.status
                if is_successful_charge(charge):
                    payment.status = PaymentStatus.COMPLETED
                    await sync_payment(connection, payment, payment.invoice, customer)
                elif charge.status in {"DECLINED", "FAILED", "CANCELLED"}:
                    payment.status = PaymentStatus.FAILED
                payment.quickbooks_reconciled_at = _now()
                payment.quickbooks_sync_error = None
                results["reconciled"] += 1
            except (QuickBooksAccountingError, QuickBooksPaymentError, QuickBooksOAuthError) as exc:
                payment.quickbooks_sync_error = str(exc)
                results["failed"] += 1

        refund_records = (await db.execute(
            select(Payment)
            .options(
                selectinload(Payment.invoice).selectinload(Invoice.tenant),
                selectinload(Payment.invoice)
                .selectinload(Invoice.repair_order)
                .selectinload(RepairOrder.customer)
            )
            .where(
                Payment.method == PaymentMethod.QUICKBOOKS,
                Payment.quickbooks_refund_id.is_not(None),
                Payment.quickbooks_refund_receipt_id.is_(None),
                Payment.status == PaymentStatus.COMPLETED,
            )
            .limit(limit)
        )).scalars().all()
        for refund in refund_records:
            results["checked"] += 1
            connection = (await db.execute(
                select(QuickBooksConnection).where(
                    QuickBooksConnection.tenant_id == refund.tenant_id,
                    QuickBooksConnection.status == "connected",
                )
            )).scalar_one_or_none()
            customer = refund.invoice.repair_order.customer if refund.invoice and refund.invoice.repair_order else None
            if not connection or not customer:
                refund.quickbooks_sync_error = "QuickBooks refund accounting context is unavailable"
                results["failed"] += 1
                continue
            try:
                await _refresh_if_needed(connection)
                await create_refund_receipt(
                    connection,
                    refund,
                    refund.invoice,
                    customer,
                    refund_id=refund.quickbooks_refund_id or "",
                    amount=abs(Decimal(refund.amount)),
                )
                refund.quickbooks_reconciled_at = _now()
                refund.quickbooks_sync_error = None
                results["reconciled"] += 1
            except (QuickBooksAccountingError, QuickBooksOAuthError) as exc:
                refund.quickbooks_sync_error = str(exc)
                results["failed"] += 1
        await db.commit()
    return results


async def backfill_quickbooks_cdc(
    *,
    session_factory: async_sessionmaker[AsyncSession] = AsyncSessionLocal,
) -> dict[str, int]:
    """Daily recovery for missed QBO webhooks and provider-side changes."""
    results = {"connections": 0, "entities": 0, "failed": 0}
    async with session_factory() as db:
        connections = (await db.execute(
            select(QuickBooksConnection).where(
                QuickBooksConnection.status == "connected",
                QuickBooksConnection.realm_id.is_not(None),
            )
        )).scalars().all()
        for connection in connections:
            results["connections"] += 1
            changed_since = connection.last_cdc_at or (_now() - timedelta(days=1))
            try:
                await _refresh_if_needed(connection)
                changes = await change_data_capture(connection, changed_since=changed_since)
                for entity in changes.get("Invoice", []):
                    provider_id = str(entity.get("Id") or "")
                    invoice = (await db.execute(
                        select(Invoice).where(
                            Invoice.tenant_id == connection.tenant_id,
                            Invoice.quickbooks_invoice_id == provider_id,
                        )
                    )).scalar_one_or_none() if provider_id else None
                    if invoice:
                        invoice.quickbooks_sync_status = "synced"
                        invoice.quickbooks_synced_at = _now()
                        invoice.quickbooks_sync_error = None
                for field, entity_name in (
                    ("quickbooks_payment_id", "Payment"),
                    ("quickbooks_refund_receipt_id", "RefundReceipt"),
                ):
                    for entity in changes.get(entity_name, []):
                        provider_id = str(entity.get("Id") or "")
                        payment = (await db.execute(
                            select(Payment).where(
                                Payment.tenant_id == connection.tenant_id,
                                getattr(Payment, field) == provider_id,
                            )
                        )).scalar_one_or_none() if provider_id else None
                        if payment:
                            payment.quickbooks_reconciled_at = _now()
                            payment.quickbooks_sync_error = None
                results["entities"] += sum(len(items) for items in changes.values())
                connection.last_cdc_at = _now()
                connection.last_cdc_error = None
            except (QuickBooksAccountingError, QuickBooksOAuthError) as exc:
                connection.last_cdc_error = str(exc)
                results["failed"] += 1
        await db.commit()
    return results
