"""Provider-aware reservation expiry and pending refund reconciliation."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

import stripe
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models.inventory_lifecycle import (
    CounterSale, CounterSalePaymentAttempt, CounterSaleRefund,
    CounterSaleReservation, CounterSaleReturn,
)
from app.db.models.quickbooks_connection import QuickBooksConnection
from app.db.models.tenant import Tenant
from app.db.session import AsyncSessionLocal
from app.services.counter_sale_service import (
    finalize_checkout_failure, finalize_checkout_success,
    finalize_refund_failure, finalize_refund_success,
)
from app.services.provider_outbox_service import enqueue_email_notification
from app.services.quickbooks_payments_service import (
    QuickBooksPaymentError, get_charge, is_successful_charge, refund_charge,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _connection(db: AsyncSession, tenant_id: UUID) -> QuickBooksConnection | None:
    return (await db.execute(select(QuickBooksConnection).where(
        QuickBooksConnection.tenant_id == tenant_id,
        QuickBooksConnection.deleted_at.is_(None),
        QuickBooksConnection.status == "connected",
    ))).scalar_one_or_none()


async def _alert(
    db: AsyncSession, *, tenant: Tenant, aggregate_id: UUID,
    key: str, subject: str, body: str,
) -> None:
    if not tenant.email:
        return
    await enqueue_email_notification(
        db, tenant_id=tenant.id, aggregate_type="counter_sale_operational_alert",
        aggregate_id=aggregate_id, idempotency_key=key,
        recipient=tenant.email, subject=subject, body=body,
        template_name="counter_sale_operational_alert", sender_name=tenant.name,
    )


async def _claim_expired_attempts(db: AsyncSession, *, limit: int) -> list[UUID]:
    rows = list((await db.execute(select(CounterSalePaymentAttempt).join(
        CounterSale, CounterSale.id == CounterSalePaymentAttempt.sale_id
    ).join(
        CounterSaleReservation, CounterSaleReservation.sale_id == CounterSale.id
    ).where(
        CounterSalePaymentAttempt.state == "pending",
        CounterSale.status == "awaiting_payment",
        CounterSaleReservation.state == "held",
        CounterSaleReservation.expires_at <= _now(),
    ).order_by(CounterSaleReservation.expires_at, CounterSalePaymentAttempt.id)
      .limit(limit).with_for_update(skip_locked=True))).scalars().unique().all())
    ids = [row.id for row in rows]
    if ids:
        reservations = list((await db.execute(select(CounterSaleReservation).where(
            CounterSaleReservation.sale_id.in_([row.sale_id for row in rows]),
            CounterSaleReservation.state == "held",
        ).with_for_update())).scalars().all())
        lease = _now() + timedelta(seconds=60)
        for reservation in reservations:
            reservation.expires_at = lease
            reservation.version += 1
    await db.commit()
    return ids


async def _reconcile_expired_attempt(
    db: AsyncSession, attempt_id: UUID,
) -> str:
    attempt = await db.get(CounterSalePaymentAttempt, attempt_id)
    if attempt is None or attempt.state != "pending":
        return "skipped"
    sale = await db.get(CounterSale, attempt.sale_id)
    tenant = await db.get(Tenant, attempt.tenant_id)
    if sale is None or tenant is None:
        return "skipped"
    await db.commit()
    terminal: str | None = None
    provider_amount: Decimal | None = None
    provider_id: str | None = None
    provider_status: str | None = None
    try:
        if attempt.tender == "stripe" and attempt.provider_intent_id:
            intent = stripe.PaymentIntent.retrieve(
                attempt.provider_intent_id, stripe_account=tenant.stripe_account_id,
            )
            metadata = dict(intent.metadata or {})
            if (
                metadata.get("counter_sale_id") != str(sale.id)
                or metadata.get("tenant_id") != str(tenant.id)
                or metadata.get("attempt_id") != str(attempt.id)
            ):
                terminal = "mismatch"
            elif intent.status == "succeeded":
                terminal = "success"
                provider_amount = Decimal(intent.amount_received) / Decimal(100)
                provider_id = intent.id
                provider_status = intent.status
            elif intent.status in {"canceled", "requires_payment_method"}:
                terminal = "failed"
                provider_status = intent.status
        elif attempt.tender == "quickbooks_payments" and attempt.provider_charge_id:
            connection = await _connection(db, tenant.id)
            await db.commit()
            if connection is None:
                raise QuickBooksPaymentError("QuickBooks Payments is not connected")
            charge = await get_charge(connection=connection, charge_id=attempt.provider_charge_id)
            if is_successful_charge(charge):
                terminal = "success"
                provider_amount = charge.amount
                provider_id = charge.id
                provider_status = charge.status
            elif charge.status in {"DECLINED", "FAILED", "CANCELLED"}:
                terminal = "failed"
                provider_status = charge.status
    except (stripe.error.StripeError, QuickBooksPaymentError):
        terminal = None

    if terminal == "success" and provider_amount is not None:
        await finalize_checkout_success(
            db, tenant_id=tenant.id, sale_id=sale.id, attempt_id=attempt.id,
            provider_amount=provider_amount, currency="USD",
            provider_status=provider_status or "succeeded",
            provider_object_id=provider_id, actor=None,
        )
        await db.commit()
        return "succeeded"
    if terminal == "failed":
        await finalize_checkout_failure(
            db, tenant_id=tenant.id, sale_id=sale.id, attempt_id=attempt.id,
            failure_code=provider_status or "provider_failed", actor=None,
        )
        await db.commit()
        return "failed"

    # Unknown or mismatched provider state keeps stock held and creates one
    # durable operational signal. It never makes inventory available again.
    reservations = list((await db.execute(select(CounterSaleReservation).where(
        CounterSaleReservation.tenant_id == tenant.id,
        CounterSaleReservation.sale_id == sale.id,
        CounterSaleReservation.state == "held",
    ).with_for_update())).scalars().all())
    for reservation in reservations:
        reservation.expires_at = _now() + timedelta(minutes=5)
        reservation.version += 1
    await _alert(
        db, tenant=tenant, aggregate_id=attempt.id,
        key=f"counter-sale:{sale.id}:attempt:{attempt.id}:expiry-unknown:v1",
        subject="Counter sale payment needs reconciliation",
        body=(
            "<p>A counter-sale payment could not be safely confirmed or released. "
            f"The stock hold remains active for sale <strong>{sale.sale_number}</strong>.</p>"
        ),
    )
    await db.commit()
    return "unknown" if terminal is None else "mismatch"


async def reconcile_expired_counter_sale_reservations(
    *, session_factory: async_sessionmaker[AsyncSession] = AsyncSessionLocal,
    limit: int = 50,
) -> dict[str, int]:
    async with session_factory() as db:
        attempt_ids = await _claim_expired_attempts(db, limit=limit)
    result = {"checked": len(attempt_ids), "succeeded": 0, "failed": 0, "unknown": 0, "mismatch": 0, "skipped": 0}
    for attempt_id in attempt_ids:
        async with session_factory() as db:
            state = await _reconcile_expired_attempt(db, attempt_id)
            result[state] += 1
    return result


async def reconcile_pending_counter_sale_refunds(
    *, session_factory: async_sessionmaker[AsyncSession] = AsyncSessionLocal,
    limit: int = 50,
) -> dict[str, int]:
    result = {"checked": 0, "succeeded": 0, "failed": 0, "pending": 0}
    async with session_factory() as db:
        ids = list((await db.execute(select(CounterSaleRefund.id).join(
            CounterSaleReturn, CounterSaleReturn.id == CounterSaleRefund.return_id
        ).where(
            CounterSaleRefund.state == "pending",
            CounterSaleReturn.state == "pending_refund",
        ).order_by(CounterSaleRefund.updated_at, CounterSaleRefund.id)
          .limit(limit))).scalars().all())
    for refund_id in ids:
        result["checked"] += 1
        async with session_factory() as db:
            refund = await db.get(CounterSaleRefund, refund_id)
            return_row = await db.get(CounterSaleReturn, refund.return_id) if refund else None
            attempt = await db.get(CounterSalePaymentAttempt, refund.payment_attempt_id) if refund else None
            tenant = await db.get(Tenant, refund.tenant_id) if refund else None
            if not refund or not return_row or not attempt or not tenant:
                result["pending"] += 1
                continue
            await db.commit()
            status_value = "pending"
            provider_id = refund.provider_refund_id
            try:
                if refund.tender == "stripe":
                    response = stripe.Refund.create(
                        payment_intent=attempt.provider_intent_id,
                        amount=int(Decimal(refund.amount) * 100),
                        idempotency_key=f"db045-refund-{refund.id}-attempt-{refund.attempt_count}",
                        stripe_account=tenant.stripe_account_id,
                    )
                    provider_id = str(response.id)
                    status_value = str(response.status).lower()
                elif refund.tender == "quickbooks_payments":
                    connection = await _connection(db, tenant.id)
                    await db.commit()
                    if connection is None:
                        raise QuickBooksPaymentError("QuickBooks Payments is not connected")
                    response = await refund_charge(
                        connection=connection, charge_id=attempt.provider_charge_id or "",
                        amount=Decimal(refund.amount),
                        description=f"Counter sale return {return_row.id}",
                        request_id=f"db045-refund-{refund.id}-attempt-{refund.attempt_count}",
                    )
                    provider_id = response.id
                    status_value = response.status.lower()
            except (stripe.error.StripeError, QuickBooksPaymentError):
                status_value = "pending"
            if status_value in {"succeeded", "completed", "captured"}:
                await finalize_refund_success(
                    db, tenant_id=tenant.id, return_id=return_row.id,
                    provider_refund_id=provider_id, actor=None,
                )
                await db.commit()
                result["succeeded"] += 1
            elif status_value in {"failed", "cancelled", "canceled", "declined"}:
                await finalize_refund_failure(
                    db, tenant_id=tenant.id, return_id=return_row.id,
                    failure_code=status_value, actor=None,
                )
                await db.commit()
                result["failed"] += 1
            else:
                refund.provider_refund_id = provider_id
                await db.commit()
                result["pending"] += 1
    return result
