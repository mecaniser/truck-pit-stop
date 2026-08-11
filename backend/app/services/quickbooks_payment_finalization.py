"""Local finalization for successful QuickBooks Payments charges."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.metrics import record_payment
from app.core.websocket import broadcast_payment_received, broadcast_repair_order_update
from app.db.models.customer import Customer
from app.db.models.invoice import Invoice, InvoiceStatus
from app.db.models.payment import Payment, PaymentMethod, PaymentStatus
from app.db.models.repair_order import RepairOrder, RepairOrderStatus
from app.db.models.tenant import Tenant
from app.db.models.vehicle import Vehicle
from app.services.invoice_notification_service import send_invoice_payment_confirmation_email
from app.services.payment_number_service import allocate_next_payment_number
from app.services.quickbooks_payments_service import QuickBooksCharge
from app.services.paid_invoice_webhook_service import enqueue_paid_invoice_webhook


async def find_quickbooks_payment(db: AsyncSession, idempotency_key: str) -> Optional[Payment]:
    result = await db.execute(select(Payment).where(Payment.quickbooks_idempotency_key == idempotency_key))
    return result.scalar_one_or_none()


async def finalize_quickbooks_invoice_payment(
    *,
    db: AsyncSession,
    invoice: Invoice,
    order: RepairOrder,
    customer: Optional[Customer],
    tenant: Optional[Tenant],
    vehicle: Optional[Vehicle],
    charge: QuickBooksCharge,
    idempotency_key: str,
) -> Payment:
    existing = await find_quickbooks_payment(db, idempotency_key)
    if existing:
        return existing
    if invoice.status == InvoiceStatus.PAID:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Invoice already paid")

    invoice.zelle_pending_submitted_at = None
    invoice.zelle_pending_sender_email = None
    invoice.zelle_pending_sender_phone = None
    invoice.zelle_pending_last_reminder_at = None
    invoice.zelle_pending_reminder_count = 0
    invoice.status = InvoiceStatus.PAID
    invoice.paid_at = datetime.now(timezone.utc)
    order.status = RepairOrderStatus.PAID
    payment = Payment(
        tenant_id=invoice.tenant_id,
        invoice_id=invoice.id,
        payment_number=await allocate_next_payment_number(db, invoice.tenant_id),
        amount=charge.amount,
        method=PaymentMethod.QUICKBOOKS,
        status=PaymentStatus.COMPLETED,
        quickbooks_charge_id=charge.id,
        quickbooks_charge_status=charge.status,
        quickbooks_idempotency_key=idempotency_key,
        notes="Payment made by customer portal through QuickBooks Payments.",
    )
    db.add(payment)
    await enqueue_paid_invoice_webhook(
        db,
        tenant=tenant,
        invoice=invoice,
        order=order,
        customer=customer,
    )
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        existing = await find_quickbooks_payment(db, idempotency_key)
        if existing:
            return existing
        raise

    await db.refresh(invoice)
    await db.refresh(order)
    await broadcast_payment_received(tenant_id=str(invoice.tenant_id), customer_id=str(order.customer_id), invoice_id=str(invoice.id), order_id=str(order.id))
    await broadcast_repair_order_update(tenant_id=str(invoice.tenant_id), customer_id=str(order.customer_id), order_id=str(order.id), order_number=order.order_number, status=order.status.value, updated_at=order.updated_at.isoformat() if order.updated_at else None)
    record_payment(status="success", payment_method="quickbooks", tenant_id=str(invoice.tenant_id))
    try:
        await send_invoice_payment_confirmation_email(db=db, invoice=invoice, order=order, customer=customer, tenant=tenant, vehicle=vehicle)
    except Exception:
        pass
    return payment
