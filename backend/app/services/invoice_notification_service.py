from decimal import Decimal
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models.customer import Customer
from app.db.models.inventory import PartsUsage
from app.db.models.invoice import Invoice
from app.db.models.labor import Labor
from app.db.models.repair_order import RepairOrder
from app.db.models.tenant import Tenant
from app.db.models.vehicle import Vehicle
from app.services.email_service import send_email
from app.services.invoice_access_service import generate_invoice_access_link
from app.services.pdf_service import generate_invoice_pdf
from app.services.pricing import get_order_parts_total


async def _load_line_items(db: AsyncSession, repair_order_id) -> tuple[list, list]:
    labor_result = await db.execute(
        select(Labor).where(Labor.repair_order_id == repair_order_id)
    )
    parts_result = await db.execute(
        select(PartsUsage)
        .options(selectinload(PartsUsage.inventory_item))
        .where(PartsUsage.repair_order_id == repair_order_id)
    )
    labor_items = [
        {
            "description": l.description,
            "hours": l.hours,
            "hourly_rate": l.hourly_rate,
            "total_cost": l.total_cost,
        }
        for l in labor_result.scalars().all()
    ]
    parts_items = []
    for p in parts_result.scalars().all():
        list_price = p.list_price if p.list_price is not None else p.unit_price
        savings = (list_price - p.unit_price) * p.quantity if list_price > p.unit_price else Decimal("0")
        parts_items.append({
            "name": p.inventory_item.name if p.inventory_item else "Part",
            "quantity": p.quantity,
            "unit_price": p.unit_price,
            "list_price": list_price,
            "savings": savings,
            "total_price": p.total_price,
        })
    return labor_items, parts_items


async def send_invoice_payment_confirmation_email(
    db: AsyncSession,
    invoice: Invoice,
    order: RepairOrder,
    customer: Customer,
    tenant: Optional[Tenant],
    vehicle: Optional[Vehicle],
) -> None:
    """Send a PAID invoice confirmation email with PDF attached."""
    if not customer.email:
        return

    shop_name = tenant.name if tenant else "Your Shop"
    shop_phone = tenant.phone if tenant else ""
    shop_email_addr = tenant.email if tenant else ""
    vehicle_info = f"{vehicle.year or ''} {vehicle.make} {vehicle.model}".strip() if vehicle else "Vehicle"
    paid_on = invoice.paid_at.strftime("%m/%d/%Y") if invoice.paid_at else "Today"
    total = Decimal(str(invoice.total_amount))

    invoice_access_url = await generate_invoice_access_link(
        invoice=invoice,
        order=order,
        customer=customer,
        shop_name=tenant.name if tenant else None,
        shop_phone=tenant.phone if tenant else None,
        shop_email=tenant.email if tenant else None,
        shop_logo_url=tenant.logo_url if tenant else None,
    )

    labor_items, parts_items = await _load_line_items(db, order.id)

    # ── Email HTML ──────────────────────────────────────────────────────────────
    def item_rows_html(items, is_labor: bool) -> str:
        html = ""
        for item in items:
            if is_labor:
                hrs = float(item.get("hours", 0))
                rate = Decimal(str(item.get("hourly_rate", 0)))
                total_item = Decimal(str(item.get("total_cost", 0)))
                qty = f"{hrs:.1f} hr{'s' if hrs != 1 else ''}"
                desc = item.get("description", "")
            else:
                qty = str(item.get("quantity", 1))
                rate = Decimal(str(item.get("unit_price", 0)))
                total_item = Decimal(str(item.get("total_price", 0)))
                desc = item.get("name", "")
            html += f"""
            <tr>
              <td style="padding:6px 8px;color:#374151;border-bottom:1px solid #f3f4f6;">{desc}</td>
              <td style="padding:6px 8px;color:#6b7280;text-align:right;border-bottom:1px solid #f3f4f6;">{qty}</td>
              <td style="padding:6px 8px;color:#6b7280;text-align:right;border-bottom:1px solid #f3f4f6;">${rate:,.2f}</td>
              <td style="padding:6px 8px;color:#1f2937;font-weight:600;text-align:right;border-bottom:1px solid #f3f4f6;">${total_item:,.2f}</td>
            </tr>"""
        return html

    def section_header_html(label: str) -> str:
        return f'<tr><td colspan="4" style="padding:8px 8px 4px 8px;background:#f3f4f6;font-weight:700;font-size:12px;color:#374151;border-bottom:1px solid #e5e7eb;">{label}</td></tr>'

    items_html = ""
    if labor_items:
        items_html += section_header_html("Labor")
        items_html += item_rows_html(labor_items, is_labor=True)
    if parts_items:
        items_html += section_header_html("Parts")
        items_html += item_rows_html(parts_items, is_labor=False)

    shop_supplies = Decimal(str(invoice.shop_supplies_amount or 0))
    service_fee = Decimal(str(invoice.service_fee_amount or 0))
    if shop_supplies > 0 or service_fee > 0:
        items_html += section_header_html("Fees")
    if shop_supplies > 0:
        items_html += f'<tr><td style="padding:6px 8px;color:#374151;border-bottom:1px solid #f3f4f6;">Shop Supplies</td><td style="padding:6px 8px;text-align:right;border-bottom:1px solid #f3f4f6;"></td><td style="padding:6px 8px;text-align:right;border-bottom:1px solid #f3f4f6;"></td><td style="padding:6px 8px;color:#1f2937;font-weight:600;text-align:right;border-bottom:1px solid #f3f4f6;">${shop_supplies:,.2f}</td></tr>'
    if service_fee > 0:
        items_html += f'<tr><td style="padding:6px 8px;color:#374151;border-bottom:1px solid #f3f4f6;">Processing Fee</td><td style="padding:6px 8px;text-align:right;border-bottom:1px solid #f3f4f6;"></td><td style="padding:6px 8px;text-align:right;border-bottom:1px solid #f3f4f6;"></td><td style="padding:6px 8px;color:#1f2937;font-weight:600;text-align:right;border-bottom:1px solid #f3f4f6;">${service_fee:,.2f}</td></tr>'

    discount = Decimal(str(invoice.discount_amount or 0))
    tax = Decimal(str(invoice.tax_amount or 0))
    subtotal = Decimal(str(invoice.subtotal))
    discount_row = f'<tr><td colspan="3" style="padding:4px 8px;text-align:right;color:#16a34a;">Discount</td><td style="padding:4px 8px;text-align:right;color:#16a34a;font-weight:600;">-${discount:,.2f}</td></tr>' if discount > 0 else ""

    shop_contact = ""
    if shop_phone:
        shop_contact += f" &nbsp;·&nbsp; {shop_phone}"
    if shop_email_addr:
        shop_contact += f" &nbsp;·&nbsp; {shop_email_addr}"

    html_body = f"""
<div style="font-family:Arial,sans-serif;max-width:640px;margin:0 auto;background:#ffffff;">

  <!-- Header -->
  <div style="background:#16a34a;padding:24px 28px;border-radius:8px 8px 0 0;">
    <table width="100%" cellpadding="0" cellspacing="0">
      <tr>
        <td>
          <span style="color:#ffffff;font-size:20px;font-weight:700;">Payment Received</span><br>
          <span style="color:#bbf7d0;font-size:13px;">{invoice.invoice_number} &nbsp;·&nbsp; Paid {paid_on}</span>
        </td>
        <td align="right"><span style="color:#f0fdf4;font-size:18px;font-weight:700;">{shop_name}</span></td>
      </tr>
    </table>
  </div>

  <!-- Summary -->
  <div style="background:#f0fdf4;padding:20px 28px;border-bottom:1px solid #bbf7d0;">
    <table width="100%" cellpadding="0" cellspacing="0">
      <tr>
        <td style="vertical-align:top;width:50%;">
          <p style="margin:0 0 2px 0;font-size:10px;font-weight:700;color:#6b7280;text-transform:uppercase;letter-spacing:.5px;">Billed To</p>
          <p style="margin:0 0 2px 0;font-size:14px;font-weight:700;color:#1f2937;">{customer.first_name} {customer.last_name}</p>
          <p style="margin:0;font-size:12px;color:#6b7280;">{vehicle_info}</p>
        </td>
        <td style="vertical-align:top;text-align:right;">
          <p style="margin:0 0 4px 0;font-size:12px;color:#6b7280;"><b>Order #:</b> {order.order_number}</p>
          <p style="margin:0;font-size:22px;font-weight:700;color:#16a34a;">${total:,.2f}</p>
          <p style="margin:0;font-size:11px;color:#6b7280;">Amount Paid</p>
        </td>
      </tr>
    </table>
  </div>

  <!-- Line items -->
  <div style="padding:20px 28px 0 28px;">
    <table width="100%" cellpadding="0" cellspacing="0" style="border:1px solid #e5e7eb;border-radius:6px;overflow:hidden;">
      <thead>
        <tr style="background:#1f2937;">
          <th style="padding:8px;color:#fff;font-size:11px;text-align:left;font-weight:700;">Description</th>
          <th style="padding:8px;color:#fff;font-size:11px;text-align:right;font-weight:700;">Qty/Hrs</th>
          <th style="padding:8px;color:#fff;font-size:11px;text-align:right;font-weight:700;">Rate</th>
          <th style="padding:8px;color:#fff;font-size:11px;text-align:right;font-weight:700;">Total</th>
        </tr>
      </thead>
      <tbody>{items_html}</tbody>
    </table>
  </div>

  <!-- Totals -->
  <div style="padding:12px 28px 20px 28px;">
    <table width="100%" cellpadding="0" cellspacing="0">
      <tr><td colspan="3" style="padding:4px 8px;text-align:right;color:#6b7280;">Subtotal</td><td style="padding:4px 8px;text-align:right;color:#374151;">${subtotal:,.2f}</td></tr>
      {discount_row}
      <tr><td colspan="3" style="padding:4px 8px;text-align:right;color:#6b7280;">Tax</td><td style="padding:4px 8px;text-align:right;color:#374151;">${tax:,.2f}</td></tr>
      <tr style="background:#16a34a;">
        <td colspan="3" style="padding:10px 8px;text-align:right;color:#fff;font-weight:700;font-size:15px;">TOTAL PAID</td>
        <td style="padding:10px 8px;text-align:right;color:#fff;font-weight:700;font-size:15px;">${total:,.2f}</td>
      </tr>
    </table>
  </div>

  <!-- CTA -->
  <div style="padding:0 28px 24px 28px;text-align:center;">
    <a href="{invoice_access_url}" style="display:inline-block;background:#16a34a;color:#fff;padding:13px 32px;text-decoration:none;border-radius:8px;font-weight:700;font-size:15px;">
      View Invoice Receipt
    </a>
    <p style="color:#9ca3af;font-size:11px;margin-top:10px;">Your paid invoice PDF is attached for your records.</p>
  </div>

  <!-- Footer -->
  <div style="background:#f3f4f6;padding:16px 28px;border-radius:0 0 8px 8px;text-align:center;">
    <p style="margin:0;font-size:12px;color:#6b7280;">{shop_name}{shop_contact}</p>
    <p style="margin:6px 0 0 0;font-size:11px;color:#9ca3af;">Thank you for your business!</p>
    <p style="margin:10px 0 0 0;font-size:10px;color:#d1d5db;">Powered by DieselBridge Network</p>
  </div>

</div>
"""

    # ── PDF ─────────────────────────────────────────────────────────────────────
    attachments = None
    try:
        service_date = order.work_completed_at.strftime("%m/%d/%Y") if order.work_completed_at else None
        due_date_str = invoice.due_date.strftime("%m/%d/%Y") if invoice.due_date and hasattr(invoice.due_date, "strftime") else (str(invoice.due_date) if invoice.due_date else None)
        tax_rate = float(tenant.sales_tax_rate) if tenant and tenant.sales_tax_rate else None

        pdf_bytes = generate_invoice_pdf(
            invoice_number=invoice.invoice_number,
            order_number=order.order_number,
            invoice_date=invoice.created_at.strftime("%m/%d/%Y") if invoice.created_at else "",
            service_completed=service_date,
            due_date=due_date_str,
            status=invoice.status.value if hasattr(invoice.status, "value") else str(invoice.status),
            notes=invoice.notes,
            customer_company=getattr(customer, "company_name", None),
            customer_name=f"{customer.first_name} {customer.last_name}",
            customer_email=customer.email,
            customer_phone=customer.phone,
            shop_name=shop_name,
            shop_address=tenant.address if tenant else None,
            shop_email=tenant.email if tenant else None,
            shop_phone=tenant.phone if tenant else None,
            shop_logo_url=tenant.logo_url if tenant else None,
            vehicle_year=str(vehicle.year) if vehicle and vehicle.year else None,
            vehicle_make=vehicle.make if vehicle else "",
            vehicle_model=vehicle.model if vehicle else "",
            vehicle_unit=getattr(vehicle, "unit_number", None),
            vehicle_vin=getattr(vehicle, "vin", None),
            vehicle_odometer=getattr(vehicle, "odometer", None),
            labor_items=labor_items,
            parts_items=parts_items,
            labor_total=Decimal(str(invoice.subtotal)) - get_order_parts_total(order),
            parts_total=get_order_parts_total(order),
            shop_supplies_amount=shop_supplies,
            service_fee_amount=service_fee,
            subtotal=subtotal,
            tax_amount=tax,
            tax_rate=tax_rate,
            discount_amount=discount,
            total_amount=total,
            invoice_access_url=invoice_access_url,
            zelle_email=tenant.zelle_email if tenant else None,
            zelle_phone=tenant.zelle_phone if tenant else None,
        )
        attachments = [{"filename": f"Invoice-{invoice.invoice_number}-PAID.pdf", "content": pdf_bytes}]
    except Exception:
        pass

    await send_email(
        db=db,
        tenant_id=str(invoice.tenant_id),
        to=customer.email,
        subject=f"Payment Received – {invoice.invoice_number} ({shop_name})",
        body=html_body,
        template_name="invoice_paid_confirmation",
        attachments=attachments,
    )
