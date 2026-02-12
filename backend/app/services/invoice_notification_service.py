from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.customer import Customer
from app.db.models.invoice import Invoice
from app.db.models.repair_order import RepairOrder
from app.db.models.tenant import Tenant
from app.db.models.vehicle import Vehicle
from app.services.email_service import send_email
from app.services.invoice_access_service import generate_invoice_access_link


async def send_invoice_payment_confirmation_email(
    db: AsyncSession,
    invoice: Invoice,
    order: RepairOrder,
    customer: Customer,
    tenant: Optional[Tenant],
    vehicle: Optional[Vehicle],
) -> None:
    """Send a paid-invoice confirmation email with a fresh invoice link."""
    if not customer.email:
        return

    vehicle_info = f"{vehicle.year or ''} {vehicle.make} {vehicle.model}".strip() if vehicle else "Vehicle"
    invoice_access_url = await generate_invoice_access_link(
        invoice=invoice,
        order=order,
        customer=customer,
        shop_name=tenant.name if tenant else None,
        shop_phone=tenant.phone if tenant else None,
        shop_email=tenant.email if tenant else None,
    )

    html_body = f"""
    <html>
    <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
        <h1 style="color: #16a34a; margin-bottom: 10px;">Payment Received</h1>
        <p>Hi {customer.first_name},</p>
        <p>We received your payment for invoice <strong>{invoice.invoice_number}</strong>.</p>

        <div style="background: #f3f4f6; border-radius: 8px; padding: 20px; margin: 20px 0;">
            <p style="margin: 0 0 10px 0;"><strong>Invoice #:</strong> {invoice.invoice_number}</p>
            <p style="margin: 0 0 10px 0;"><strong>Order #:</strong> {order.order_number}</p>
            <p style="margin: 0 0 10px 0;"><strong>Vehicle:</strong> {vehicle_info}</p>
            <p style="margin: 0 0 10px 0;"><strong>Paid On:</strong> {invoice.paid_at.strftime('%B %d, %Y') if invoice.paid_at else 'Today'}</p>
            <p style="margin: 0; font-size: 24px; color: #1f2937;"><strong>Total Paid: ${invoice.total_amount:.2f}</strong></p>
        </div>

        <p>You can view your invoice copy anytime here:</p>
        <p style="margin: 20px 0;">
            <a href="{invoice_access_url}"
               style="display: inline-block; background: #16a34a; color: white; padding: 12px 24px; text-decoration: none; border-radius: 8px; font-weight: bold;">
                View Paid Invoice
            </a>
        </p>

        <p style="color: #6b7280; font-size: 14px; margin-top: 30px;">
            Thank you for your business.
        </p>
    </body>
    </html>
    """

    await send_email(
        db=db,
        tenant_id=str(invoice.tenant_id),
        to=customer.email,
        subject=f"Payment Received - Invoice {invoice.invoice_number}",
        body=html_body,
        template_name="invoice_paid_confirmation",
    )
