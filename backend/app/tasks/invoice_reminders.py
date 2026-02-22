"""
Invoice reminder task - sends reminders for overdue unpaid invoices.

Schedule: Runs daily
Logic:
- Finds invoices where due_date < today and status != PAID
- Respects per-tenant settings: enabled, frequency, max reminders
- Sends reminder on due date, then per tenant's frequency setting
"""
import asyncio
from datetime import date, datetime, timedelta, timezone
from app.tasks import celery_app
from app.db.session import AsyncSessionLocal
from app.db.models.invoice import Invoice, InvoiceStatus
from app.db.models.customer import Customer
from app.db.models.vehicle import Vehicle
from app.db.models.repair_order import RepairOrder
from app.db.models.tenant import Tenant
from app.services.email_service import send_email
from app.services.invoice_access_service import generate_invoice_access_link
from app.services.twilio_service import send_sms
from sqlalchemy import select, and_
from sqlalchemy.orm import selectinload
# Fallback defaults if tenant settings are missing
DEFAULT_MAX_REMINDERS = 3
DEFAULT_REMINDER_INTERVAL_DAYS = 3


async def _process_invoice_reminders(tenant_id: str = None):
    """
    Core async logic for processing invoice reminders.
    
    Args:
        tenant_id: Optional UUID string. If provided, only process invoices for this tenant.
                   If None (scheduled task), processes all tenants.
    
    Respects per-tenant settings:
        - invoice_reminders_enabled: skip tenant if False
        - reminder_frequency_days: days between reminders
        - max_invoice_reminders: max reminders per invoice
    """
    async with AsyncSessionLocal() as db:
        today = date.today()
        now = datetime.now(timezone.utc)
        
        # Find overdue unpaid invoices that need reminders
        # Conditions:
        # 1. status is SENT or OVERDUE (not PAID, DRAFT, CANCELLED)
        # 2. due_date <= today
        # 3. If tenant_id provided, filter to that tenant only
        # Note: max_reminders check is done per-invoice based on tenant settings
        
        conditions = [
            Invoice.status.in_([InvoiceStatus.SENT, InvoiceStatus.OVERDUE]),
            Invoice.due_date <= today,
            Invoice.zelle_pending_submitted_at.is_(None),
        ]
        
        # Add tenant filter if specified (for manual triggers by garage owners)
        if tenant_id:
            from uuid import UUID
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
        
        sent_count = 0
        for invoice in invoices:
            tenant = invoice.tenant
            
            # Check tenant settings
            reminders_enabled = getattr(tenant, 'invoice_reminders_enabled', True)
            max_reminders = getattr(tenant, 'max_invoice_reminders', DEFAULT_MAX_REMINDERS)
            frequency_days = getattr(tenant, 'reminder_frequency_days', DEFAULT_REMINDER_INTERVAL_DAYS)
            
            # Skip if tenant has reminders disabled
            if not reminders_enabled:
                continue
            
            # Skip if max reminders reached for this invoice
            if invoice.reminder_count >= max_reminders:
                continue
            
            # Check if enough time has passed since last reminder (per tenant frequency)
            if invoice.last_reminder_sent_at:
                days_since_last = (now - invoice.last_reminder_sent_at).days
                if days_since_last < frequency_days:
                    continue
            
            # Get related data
            repair_order = invoice.repair_order
            customer = repair_order.customer if repair_order else None
            vehicle = repair_order.vehicle if repair_order else None
            tenant = invoice.tenant
            
            if not customer:
                continue
            
            # Update invoice status to OVERDUE if not already
            if invoice.status != InvoiceStatus.OVERDUE:
                invoice.status = InvoiceStatus.OVERDUE
            
            # Build reminder message
            vehicle_info = f"{vehicle.year or ''} {vehicle.make} {vehicle.model}".strip() if vehicle else "your vehicle"
            days_overdue = (today - invoice.due_date.date()).days if invoice.due_date else 0
            garage_name = tenant.name if tenant else "DieselBridge Network"
            
            reminder_num = invoice.reminder_count + 1
            
            # Send SMS if customer has phone
            if customer.phone:
                if reminder_num == 1:
                    sms_body = f"Reminder: Invoice #{invoice.invoice_number} for ${invoice.total_amount:,.2f} ({vehicle_info}) is due today. Please pay at your earliest convenience. - {garage_name}"
                else:
                    sms_body = f"Reminder #{reminder_num}: Invoice #{invoice.invoice_number} for ${invoice.total_amount:,.2f} is {days_overdue} days overdue. Please pay ASAP to avoid service holds. - {garage_name}"
                
                try:
                    await send_sms(
                        db,
                        str(invoice.tenant_id),
                        customer.phone,
                        sms_body,
                        template_name="invoice_reminder_sms",
                        customer_id=customer.id,
                        source="automated",
                    )
                except Exception:
                    pass
            
            # Send email if customer has email (and not a placeholder)
            if customer.email and "@placeholder" not in customer.email:
                invoice_access_url = await generate_invoice_access_link(
                    invoice=invoice,
                    order=repair_order,
                    customer=customer,
                    shop_name=tenant.name if tenant else None,
                    shop_phone=tenant.phone if tenant else None,
                    shop_email=tenant.email if tenant else None,
                )
                
                if reminder_num == 1:
                    subject = f"Payment Reminder: Invoice #{invoice.invoice_number} Due Today"
                    urgency_text = "is due today"
                else:
                    subject = f"OVERDUE: Invoice #{invoice.invoice_number} - {days_overdue} Days Past Due"
                    urgency_text = f"is <strong>{days_overdue} days overdue</strong>"
                
                html_body = f"""
                <html>
                <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
                    <h1 style="color: #d97706;">🔧 {garage_name}</h1>
                    <h2 style="color: {'#dc2626' if reminder_num > 1 else '#f59e0b'};">Payment Reminder</h2>
                    
                    <p>Hi {customer.first_name},</p>
                    <p>This is a friendly reminder that your invoice {urgency_text}.</p>
                    
                    <div style="background: #fef3c7; border-radius: 8px; padding: 20px; margin: 20px 0; border: 1px solid #fcd34d;">
                        <p style="margin: 0 0 10px 0;"><strong>Invoice #:</strong> {invoice.invoice_number}</p>
                        <p style="margin: 0 0 10px 0;"><strong>Vehicle:</strong> {vehicle_info}</p>
                        <p style="margin: 0 0 10px 0;"><strong>Amount Due:</strong> <span style="font-size: 18px; color: #dc2626;">${invoice.total_amount:,.2f}</span></p>
                        <p style="margin: 0;"><strong>Due Date:</strong> {invoice.due_date.strftime('%B %d, %Y') if invoice.due_date else 'N/A'}</p>
                    </div>
                    
                    <p>Please pay at your earliest convenience to avoid any service delays on future repairs.</p>
                    
                    <p style="margin: 30px 0; text-align: center;">
                        <a href="{invoice_access_url}" 
                           style="background-color: #d97706; color: white; padding: 12px 24px; text-decoration: none; border-radius: 6px; display: inline-block;">
                            View Invoice & Pay
                        </a>
                    </p>
                    
                    <p style="color: #666; font-size: 12px;">
                        If you've already paid, please disregard this message. 
                        Contact us if you have any questions about your invoice.
                    </p>
                </body>
                </html>
                """
                
                try:
                    await send_email(
                        db, str(invoice.tenant_id), customer.email, subject, html_body,
                        template_name="invoice_reminder_email"
                    )
                except Exception:
                    pass
            
            # Update tracking fields
            invoice.last_reminder_sent_at = now
            invoice.reminder_count = reminder_num
            sent_count += 1
        
        await db.commit()
        return sent_count


@celery_app.task(name="process_invoice_reminders")
def process_invoice_reminders():
    """Celery task wrapper - runs the async reminder logic"""
    loop = asyncio.get_event_loop()
    if loop.is_closed():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    try:
        count = loop.run_until_complete(_process_invoice_reminders())
        return {"status": "success", "reminders_sent": count}
    except Exception as e:
        return {"status": "error", "message": str(e)}
