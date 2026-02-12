"""
Pending Zelle reminder task.

Sends staff reminders when a customer-submitted Zelle payment has not been
confirmed by staff after 24h and 48h.
"""
import asyncio
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.orm import selectinload

from app.db.models.invoice import Invoice, InvoiceStatus
from app.db.models.repair_order import RepairOrder
from app.db.session import AsyncSessionLocal
from app.services.pending_zelle_staff_notification_service import send_pending_zelle_reminder_alert
from app.tasks import celery_app


async def _process_pending_zelle_reminders(tenant_id: str = None):
    async with AsyncSessionLocal() as db:
        now = datetime.now(timezone.utc)
        conditions = [
            Invoice.zelle_pending_submitted_at.is_not(None),
            Invoice.status != InvoiceStatus.PAID,
        ]
        if tenant_id:
            conditions.append(Invoice.tenant_id == UUID(tenant_id))

        result = await db.execute(
            select(Invoice)
            .options(
                selectinload(Invoice.repair_order).selectinload(RepairOrder.customer),
                selectinload(Invoice.repair_order).selectinload(RepairOrder.vehicle),
                selectinload(Invoice.tenant),
            )
            .where(and_(*conditions))
        )
        invoices = result.scalars().all()

        reminders_sent = 0
        for invoice in invoices:
            if not invoice.zelle_pending_submitted_at:
                continue

            elapsed_hours = int((now - invoice.zelle_pending_submitted_at).total_seconds() // 3600)
            target_reminder_count = 0
            if elapsed_hours >= 48:
                target_reminder_count = 2
            elif elapsed_hours >= 24:
                target_reminder_count = 1

            if target_reminder_count == 0:
                continue
            if invoice.zelle_pending_reminder_count >= target_reminder_count:
                continue

            reminder_stage_hours = 24 if invoice.zelle_pending_reminder_count == 0 else 48
            order = invoice.repair_order
            customer = order.customer if order else None
            tenant = invoice.tenant
            if not order or not tenant:
                continue

            customer_name = (
                f"{customer.first_name} {customer.last_name}".strip()
                if customer
                else "Unknown customer"
            )
            await send_pending_zelle_reminder_alert(
                db=db,
                tenant_id=invoice.tenant_id,
                order_id=order.id,
                order_number=order.order_number,
                invoice_number=invoice.invoice_number,
                customer_name=customer_name,
                amount=invoice.total_amount,
                reminder_stage_hours=reminder_stage_hours,
            )

            invoice.zelle_pending_last_reminder_at = now
            invoice.zelle_pending_reminder_count = target_reminder_count
            reminders_sent += 1

        await db.commit()
        return reminders_sent


@celery_app.task(name="process_pending_zelle_reminders")
def process_pending_zelle_reminders():
    loop = asyncio.get_event_loop()
    if loop.is_closed():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    try:
        count = loop.run_until_complete(_process_pending_zelle_reminders())
        return {"status": "success", "reminders_sent": count}
    except Exception as e:
        return {"status": "error", "message": str(e)}
