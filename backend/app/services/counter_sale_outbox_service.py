"""Durable DB-045 accounting, receipt-email, and compensation delivery."""
from __future__ import annotations

import html
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID, uuid4

import stripe
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import settings
from app.db.models.customer import Customer
from app.db.models.inventory_lifecycle import (
    CounterSale, CounterSaleLine, CounterSalePaymentAttempt,
    CounterSaleReturn, CounterSaleReturnLine,
)
from app.db.models.provider_outbox import ProviderOutboxEvent, ProviderOutboxStatus
from app.db.models.quickbooks_connection import QuickBooksConnection
from app.db.models.tenant import Tenant
from app.db.session import AsyncSessionLocal
from app.services.provider_outbox_service import enqueue_email_notification
from app.services.part_activity_service import append_part_activity
from app.services.quickbooks_accounting_service import (
    QuickBooksAccountingError, sync_counter_sale_receipt,
    sync_counter_sale_refund_receipt,
)
from app.services.quickbooks_payments_service import QuickBooksPaymentError, refund_charge
from app.services.quickbooks_service import QuickBooksOAuthError, refresh_access_token, save_token_set


EVENT_TYPES = frozenset({
    "quickbooks.counter_sale.sync.v1",
    "quickbooks.counter_sale_return.sync.v1",
    "counter_sale.receipt.email.v1",
    "counter_sale.compensating_refund.v1",
})


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _retry_at(attempt: int) -> datetime:
    return _now() + timedelta(minutes=min(60, 2 ** max(attempt, 1)))


async def _refresh_if_needed(connection: QuickBooksConnection) -> None:
    if not connection.access_token_expires_at or connection.access_token_expires_at > _now() + timedelta(minutes=5):
        return
    token_set = await refresh_access_token(connection)
    save_token_set(connection, realm_id=connection.realm_id or "", token_set=token_set)
    connection.last_token_refresh_at = _now()
    connection.last_token_refresh_error = None


async def _claim(
    db: AsyncSession, *, limit: int,
) -> list[UUID]:
    due = or_(
        ProviderOutboxEvent.status == ProviderOutboxStatus.PENDING.value,
        (
            (ProviderOutboxEvent.status == ProviderOutboxStatus.PROCESSING.value)
            & ProviderOutboxEvent.locked_until.is_not(None)
            & (ProviderOutboxEvent.locked_until <= _now())
        ),
    )
    rows = list((await db.execute(select(ProviderOutboxEvent).where(
        ProviderOutboxEvent.event_type.in_(EVENT_TYPES),
        ProviderOutboxEvent.available_at <= _now(), due,
    ).order_by(ProviderOutboxEvent.available_at, ProviderOutboxEvent.created_at)
      .limit(limit).with_for_update(skip_locked=True))).scalars().all())
    for row in rows:
        row.status = ProviderOutboxStatus.PROCESSING.value
        row.attempt_count += 1
        row.locked_at = _now()
        row.locked_until = _now() + timedelta(seconds=settings.PROVIDER_OUTBOX_LEASE_SECONDS)
        row.lock_token = uuid4().hex
    await db.commit()
    return [row.id for row in rows]


def _receipt_html(tenant: Tenant, sale: CounterSale) -> str:
    snapshot = sale.receipt_snapshot or {}
    lines = "".join(
        "<tr>"
        f"<td>{html.escape(str(row.get('name') or row.get('sku') or 'Part'))}</td>"
        f"<td>{html.escape(str(row.get('quantity') or ''))}</td>"
        f"<td>${html.escape(str(row.get('total') or '0.00'))}</td>"
        "</tr>"
        for row in snapshot.get("lines", []) if isinstance(row, dict)
    )
    return (
        f"<h2>{html.escape(tenant.name)} receipt {html.escape(sale.sale_number)}</h2>"
        "<table><thead><tr><th>Part</th><th>Qty</th><th>Total</th></tr></thead>"
        f"<tbody>{lines}</tbody></table>"
        f"<p>Subtotal: ${html.escape(str(snapshot.get('subtotal') or '0.00'))}<br>"
        f"Tax: ${html.escape(str(snapshot.get('tax') or '0.00'))}<br>"
        f"Service fee: ${html.escape(str(snapshot.get('service_fee') or '0.00'))}<br>"
        f"<strong>Total: ${html.escape(str(snapshot.get('total') or '0.00'))}</strong></p>"
    )


async def _process_qbo_sale(db: AsyncSession, event: ProviderOutboxEvent) -> None:
    sale = await db.get(CounterSale, event.aggregate_id)
    tenant = await db.get(Tenant, event.tenant_id)
    connection = (await db.execute(select(QuickBooksConnection).where(
        QuickBooksConnection.tenant_id == event.tenant_id,
        QuickBooksConnection.status == "connected",
        QuickBooksConnection.deleted_at.is_(None),
    ))).scalar_one_or_none()
    if sale is None or tenant is None or sale.status not in {"completed", "partially_returned", "returned"}:
        raise QuickBooksAccountingError("Counter-sale accounting context is unavailable")
    if connection is None:
        raise QuickBooksAccountingError("QuickBooks is not connected", retryable=True)
    customer = None
    if sale.customer_id:
        customer = (await db.execute(select(Customer).where(
            Customer.id == sale.customer_id, Customer.tenant_id == event.tenant_id,
            Customer.deleted_at.is_(None),
        ))).scalar_one_or_none()
        if customer is None:
            raise QuickBooksAccountingError("Counter-sale customer is unavailable")
    lines = list((await db.execute(select(CounterSaleLine).where(
        CounterSaleLine.tenant_id == event.tenant_id,
        CounterSaleLine.sale_id == sale.id,
        CounterSaleLine.deleted_at.is_(None),
    ).order_by(CounterSaleLine.id))).scalars().all())
    await db.commit()
    await _refresh_if_needed(connection)
    await sync_counter_sale_receipt(connection, tenant, sale, lines, customer)


async def _process_qbo_return(db: AsyncSession, event: ProviderOutboxEvent) -> None:
    return_row = await db.get(CounterSaleReturn, event.aggregate_id)
    if return_row is None or return_row.state != "completed":
        raise QuickBooksAccountingError("Counter-sale return context is unavailable")
    sale = await db.get(CounterSale, return_row.sale_id)
    tenant = await db.get(Tenant, event.tenant_id)
    connection = (await db.execute(select(QuickBooksConnection).where(
        QuickBooksConnection.tenant_id == event.tenant_id,
        QuickBooksConnection.status == "connected",
        QuickBooksConnection.deleted_at.is_(None),
    ))).scalar_one_or_none()
    if sale is None or tenant is None or connection is None:
        raise QuickBooksAccountingError("QuickBooks return context is unavailable", retryable=True)
    customer = None
    if sale.customer_id:
        customer = (await db.execute(select(Customer).where(
            Customer.id == sale.customer_id, Customer.tenant_id == event.tenant_id,
            Customer.deleted_at.is_(None),
        ))).scalar_one_or_none()
        if customer is None:
            raise QuickBooksAccountingError("Counter-sale customer is unavailable")
    return_lines = list((await db.execute(select(CounterSaleReturnLine).where(
        CounterSaleReturnLine.tenant_id == event.tenant_id,
        CounterSaleReturnLine.return_id == return_row.id,
    ))).scalars().all())
    sale_line_ids = {row.sale_line_id for row in return_lines}
    sale_lines = {row.id: row for row in (await db.execute(select(CounterSaleLine).where(
        CounterSaleLine.tenant_id == event.tenant_id,
        CounterSaleLine.id.in_(sale_line_ids),
    ))).scalars().all()}
    if len(sale_lines) != len(sale_line_ids):
        raise QuickBooksAccountingError("Counter-sale return lines are unavailable")
    await db.commit()
    await _refresh_if_needed(connection)
    await sync_counter_sale_refund_receipt(
        connection, tenant, sale, return_row, return_lines, sale_lines, customer,
    )


async def _process_receipt_email(db: AsyncSession, event: ProviderOutboxEvent) -> None:
    sale = await db.get(CounterSale, event.aggregate_id)
    tenant = await db.get(Tenant, event.tenant_id)
    if (
        sale is None or tenant is None or not sale.receipt_snapshot
        or sale.status not in {"completed", "partially_returned", "returned"}
        or not sale.receipt_email_to
    ):
        raise RuntimeError("Completed receipt email context is unavailable")
    await enqueue_email_notification(
        db, tenant_id=event.tenant_id, aggregate_type="counter_sale_receipt",
        aggregate_id=sale.id,
        idempotency_key=f"{event.idempotency_key}:delivery",
        recipient=sale.receipt_email_to,
        subject=f"{tenant.name} receipt {sale.sale_number}",
        body=_receipt_html(tenant, sale), template_name="counter_sale_receipt",
        sender_name=tenant.name,
    )


async def _process_compensation(db: AsyncSession, event: ProviderOutboxEvent) -> None:
    attempt = await db.get(CounterSalePaymentAttempt, event.aggregate_id)
    tenant = await db.get(Tenant, event.tenant_id)
    if attempt is None or tenant is None:
        raise RuntimeError("Compensating refund context is unavailable")
    if attempt.state == "compensated":
        return
    if attempt.state != "compensating_refund_pending":
        raise RuntimeError("Compensating refund state is invalid")
    if attempt.tender == "stripe":
        await db.commit()
        result = stripe.Refund.create(
            payment_intent=attempt.provider_intent_id or attempt.provider_charge_id,
            amount=int(Decimal(attempt.amount) * 100),
            idempotency_key=f"db045-compensating-refund-{attempt.id}",
            stripe_account=tenant.stripe_account_id,
        )
        if str(result.status).lower() != "succeeded":
            raise RuntimeError("Compensating Stripe refund is pending")
        attempt.provider_reference = str(result.id)
    elif attempt.tender == "quickbooks_payments":
        connection = (await db.execute(select(QuickBooksConnection).where(
            QuickBooksConnection.tenant_id == event.tenant_id,
            QuickBooksConnection.status == "connected",
            QuickBooksConnection.deleted_at.is_(None),
        ))).scalar_one_or_none()
        if connection is None:
            raise RuntimeError("QuickBooks Payments is not connected")
        await db.commit()
        result = await refund_charge(
            connection=connection, charge_id=attempt.provider_charge_id or "",
            amount=Decimal(attempt.amount), description="Late counter-sale success reversal",
            request_id=f"db045-compensating-refund-{attempt.id}",
        )
        if result.status not in {"SUCCEEDED", "COMPLETED", "CAPTURED"}:
            raise RuntimeError("Compensating QuickBooks refund is pending")
        attempt.provider_reference = result.id
    else:
        raise RuntimeError("Automatic compensation requires a provider tender")
    attempt.state = "compensated"
    attempt.reconciled_at = _now()
    sale = await db.get(CounterSale, attempt.sale_id)
    if sale is None or sale.tenant_id != event.tenant_id:
        raise RuntimeError("Compensating refund sale context is unavailable")
    lines = list((await db.execute(select(CounterSaleLine).where(
        CounterSaleLine.tenant_id == event.tenant_id,
        CounterSaleLine.sale_id == sale.id,
        CounterSaleLine.deleted_at.is_(None),
    ).order_by(CounterSaleLine.id))).scalars().all())
    for line in lines:
        # This is intentionally emitted only after the provider refund reports
        # success.  Merely queuing compensation is not a refunded lifecycle
        # event, and this worker never changes physical stock.
        await append_part_activity(
            db, tenant_id=event.tenant_id, inventory_id=line.inventory_id,
            category="sales", event_type="counter_sale.late_success_refunded",
            idempotency_key=(
                f"counter_sale:{sale.id}:line:{line.id}:"
                f"late-success:{attempt.id}:compensated:v1"
            ),
            correlation_id=attempt.id, source_type="counter_sale",
            source_id=sale.id, source_number=sale.sale_number,
            payment={
                "tender": attempt.tender, "state": "compensated",
                "provider_object_id": (
                    attempt.provider_intent_id or attempt.provider_charge_id
                ),
            },
        )
    if tenant.email:
        await enqueue_email_notification(
            db, tenant_id=tenant.id, aggregate_type="counter_sale_operational_alert",
            aggregate_id=attempt.id,
            idempotency_key=f"counter-sale:{attempt.sale_id}:late-success-alert:v1",
            recipient=tenant.email,
            subject="Counter sale payment automatically refunded",
            body=(
                "<p>A provider confirmed a counter-sale payment after its stock hold was released. "
                "DieselBridge issued an automatic full refund. Review sale "
                f"<strong>{html.escape(str(attempt.sale_id))}</strong>.</p>"
            ),
            template_name="counter_sale_late_success_alert", sender_name=tenant.name,
        )


async def process_counter_sale_outbox_events(
    *, session_factory: async_sessionmaker[AsyncSession] = AsyncSessionLocal,
    batch_size: int = 20,
) -> dict[str, int]:
    async with session_factory() as db:
        ids = await _claim(db, limit=batch_size)
    result = {"claimed": len(ids), "succeeded": 0, "retried": 0, "dead": 0}
    for event_id in ids:
        async with session_factory() as db:
            event = await db.get(ProviderOutboxEvent, event_id)
            if event is None or event.status != ProviderOutboxStatus.PROCESSING.value:
                continue
            try:
                if event.event_type == "quickbooks.counter_sale.sync.v1":
                    await _process_qbo_sale(db, event)
                elif event.event_type == "quickbooks.counter_sale_return.sync.v1":
                    await _process_qbo_return(db, event)
                elif event.event_type == "counter_sale.receipt.email.v1":
                    await _process_receipt_email(db, event)
                else:
                    await _process_compensation(db, event)
                event.status = ProviderOutboxStatus.SUCCEEDED.value
                event.completed_at = _now()
                event.last_error = None
                event.locked_until = None
                event.lock_token = None
                result["succeeded"] += 1
            except (QuickBooksAccountingError, QuickBooksOAuthError, QuickBooksPaymentError, stripe.error.StripeError, RuntimeError) as exc:
                event.last_error = f"{type(exc).__name__}: {str(exc)[:500]}"
                event.locked_until = None
                event.lock_token = None
                if event.attempt_count >= settings.PROVIDER_OUTBOX_MAX_ATTEMPTS:
                    event.status = ProviderOutboxStatus.DEAD.value
                    event.completed_at = _now()
                    result["dead"] += 1
                    if event.event_type == "quickbooks.counter_sale.sync.v1":
                        sale = await db.get(CounterSale, event.aggregate_id)
                        if sale:
                            sale.accounting_sync_status = "error"
                else:
                    event.status = ProviderOutboxStatus.PENDING.value
                    event.available_at = _retry_at(event.attempt_count)
                    result["retried"] += 1
            await db.commit()
    return result
