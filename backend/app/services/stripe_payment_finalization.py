from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.core.metrics import record_payment
from app.core.websocket import broadcast_payment_received, broadcast_repair_order_update
from app.db.models.customer import Customer
from app.db.models.invoice import Invoice, InvoiceStatus
from app.db.models.payment import Payment, PaymentMethod as PaymentMethodEnum, PaymentStatus
from app.db.models.repair_order import RepairOrder, RepairOrderStatus
from app.db.models.tenant import Tenant
from app.db.models.vehicle import Vehicle
from app.services.invoice_notification_service import send_invoice_payment_confirmation_email
from app.services.payment_number_service import allocate_next_payment_number

logger = get_logger(__name__)


@dataclass
class StripePaymentFinalizationResult:
    invoice: Invoice
    order: RepairOrder
    payment: Payment
    created: bool


def _payment_intent_get(payment_intent: Any, key: str, default: Any = None) -> Any:
    if payment_intent is None:
        return default
    if isinstance(payment_intent, dict):
        return payment_intent.get(key, default)
    getter = getattr(payment_intent, "get", None)
    if callable(getter):
        return getter(key, default)
    return getattr(payment_intent, key, default)


def _payment_intent_metadata(payment_intent: Any) -> dict:
    metadata = _payment_intent_get(payment_intent, "metadata", {}) or {}
    return dict(metadata)


def _latest_charge_id(payment_intent: Any) -> Optional[str]:
    latest_charge = _payment_intent_get(payment_intent, "latest_charge")
    if isinstance(latest_charge, str):
        return latest_charge
    if isinstance(latest_charge, dict):
        charge_id = latest_charge.get("id")
        return charge_id if isinstance(charge_id, str) else None
    charge_id = getattr(latest_charge, "id", None)
    return charge_id if isinstance(charge_id, str) else None


async def find_stripe_payment(
    db: AsyncSession,
    payment_intent_id: str,
) -> Optional[Payment]:
    result = await db.execute(
        select(Payment).where(Payment.stripe_payment_intent_id == payment_intent_id)
    )
    return result.scalar_one_or_none()


async def finalize_stripe_invoice_payment(
    *,
    db: AsyncSession,
    invoice: Invoice,
    order: RepairOrder,
    customer: Optional[Customer],
    tenant: Optional[Tenant],
    vehicle: Optional[Vehicle],
    payment_intent: Any,
    payment_note: str,
    allow_already_paid_without_payment: bool = False,
) -> StripePaymentFinalizationResult:
    """Persist the local side effects for a succeeded Stripe invoice payment.

    This function is intentionally shared by browser confirmation and Stripe
    webhooks so the webhook is a real backup path rather than a log-only path.
    """
    payment_intent_id = _payment_intent_get(payment_intent, "id")
    if not payment_intent_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid payment intent")

    metadata = _payment_intent_metadata(payment_intent)
    if metadata.get("invoice_id") != str(invoice.id):
        logger.warning(
            "payment_intent_mismatch",
            invoice_id=str(invoice.id),
            payment_intent_invoice_id=metadata.get("invoice_id"),
            payment_intent_id=payment_intent_id,
        )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Payment intent mismatch")

    existing_payment = await find_stripe_payment(db, payment_intent_id)
    if existing_payment:
        return StripePaymentFinalizationResult(
            invoice=invoice,
            order=order,
            payment=existing_payment,
            created=False,
        )

    if invoice.status == InvoiceStatus.PAID:
        if allow_already_paid_without_payment:
            logger.info(
                "stripe_payment_succeeded_invoice_already_paid_without_matching_payment",
                invoice_id=str(invoice.id),
                payment_intent_id=payment_intent_id,
            )
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Invoice already paid")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invoice already paid")

    invoice.zelle_pending_submitted_at = None
    invoice.zelle_pending_sender_email = None
    invoice.zelle_pending_sender_phone = None
    invoice.zelle_pending_last_reminder_at = None
    invoice.zelle_pending_reminder_count = 0
    invoice.status = InvoiceStatus.PAID
    invoice.paid_at = datetime.now(timezone.utc)
    order.status = RepairOrderStatus.PAID

    payment_number = await allocate_next_payment_number(db, invoice.tenant_id)
    payment = Payment(
        tenant_id=invoice.tenant_id,
        invoice_id=invoice.id,
        payment_number=payment_number,
        amount=invoice.total_amount,
        method=PaymentMethodEnum.STRIPE,
        status=PaymentStatus.COMPLETED,
        stripe_payment_intent_id=payment_intent_id,
        stripe_charge_id=_latest_charge_id(payment_intent),
        notes=payment_note,
    )
    db.add(payment)

    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        existing_payment = await find_stripe_payment(db, payment_intent_id)
        if existing_payment:
            return StripePaymentFinalizationResult(
                invoice=invoice,
                order=order,
                payment=existing_payment,
                created=False,
            )
        raise

    await db.refresh(invoice)
    await db.refresh(order)

    await broadcast_payment_received(
        tenant_id=str(invoice.tenant_id),
        customer_id=str(order.customer_id),
        invoice_id=str(invoice.id),
        order_id=str(order.id),
    )
    await broadcast_repair_order_update(
        tenant_id=str(invoice.tenant_id),
        customer_id=str(order.customer_id),
        order_id=str(order.id),
        order_number=order.order_number,
        status=order.status.value,
        updated_at=order.updated_at.isoformat() if order.updated_at else None,
    )

    record_payment(status="success", payment_method="stripe", tenant_id=str(invoice.tenant_id))

    try:
        await send_invoice_payment_confirmation_email(
            db=db,
            invoice=invoice,
            order=order,
            customer=customer,
            tenant=tenant,
            vehicle=vehicle,
        )
    except Exception as exc:
        logger.warning(
            "invoice_paid_confirmation_email_failed",
            invoice_id=str(invoice.id),
            error=str(exc),
        )

    logger.info(
        "stripe_invoice_payment_finalized",
        invoice_id=str(invoice.id),
        payment_intent_id=payment_intent_id,
        payment_id=str(payment.id) if getattr(payment, "id", None) else None,
        amount=float(invoice.total_amount),
    )

    return StripePaymentFinalizationResult(
        invoice=invoice,
        order=order,
        payment=payment,
        created=True,
    )
