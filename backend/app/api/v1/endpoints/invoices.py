from datetime import datetime, date
from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Response, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func
from pydantic import BaseModel
from decimal import Decimal

from app.core.dependencies import get_db, get_current_active_user
from app.core.pagination import paginated_or_list
from app.db.models.user import User, UserRole
from app.db.models.repair_order import RepairOrder, RepairOrderStatus
from app.db.models.invoice import Invoice, InvoiceStatus
from app.db.models.customer import Customer
from app.db.models.vehicle import Vehicle
from app.db.models.tenant import Tenant
from app.db.models.inventory import PartsUsage
from app.db.models.labor import Labor
from app.services.pricing import get_order_labor_total, get_order_parts_total
from app.services.email_service import send_email
from app.services.invoice_access_service import generate_invoice_access_link
from app.services.pdf_service import generate_invoice_pdf
from sqlalchemy.orm import selectinload
from app.core.websocket import broadcast_invoice_created, broadcast_repair_order_update

router = APIRouter()


# ── Helpers ────────────────────────────────────────────────────────────────────

async def _load_line_items(db: AsyncSession, repair_order_id):
    """Return (labor_items, parts_items) as plain dicts for PDF / email."""
    labor_result = await db.execute(
        select(Labor).where(Labor.repair_order_id == repair_order_id)
    )
    labor_rows = labor_result.scalars().all()

    parts_result = await db.execute(
        select(PartsUsage)
        .options(selectinload(PartsUsage.inventory_item))
        .where(PartsUsage.repair_order_id == repair_order_id)
    )
    parts_rows = parts_result.scalars().all()

    labor_items = [
        {
            "description": l.description,
            "hours": l.hours,
            "hourly_rate": l.hourly_rate,
            "total_cost": l.total_cost,
        }
        for l in labor_rows
    ]
    parts_items = []
    for p in parts_rows:
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


def _build_invoice_pdf_bytes(
    invoice, order, customer, vehicle, tenant,
    labor_items, parts_items, invoice_access_url: Optional[str]
) -> bytes:
    service_date = None
    if order.work_completed_at:
        service_date = order.work_completed_at.strftime("%m/%d/%Y")
    due_date_str = None
    if invoice.due_date:
        due_date_str = invoice.due_date.strftime("%m/%d/%Y") if hasattr(invoice.due_date, "strftime") else str(invoice.due_date)

    tax_rate = float(tenant.sales_tax_rate) if tenant and tenant.sales_tax_rate else None

    return generate_invoice_pdf(
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
        shop_name=tenant.name if tenant else "Shop",
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
        shop_supplies_amount=Decimal(str(invoice.shop_supplies_amount or 0)),
        service_fee_amount=Decimal(str(invoice.service_fee_amount or 0)),
        subtotal=Decimal(str(invoice.subtotal)),
        tax_amount=Decimal(str(invoice.tax_amount)),
        tax_rate=tax_rate,
        discount_amount=Decimal(str(invoice.discount_amount or 0)),
        total_amount=Decimal(str(invoice.total_amount)),
        invoice_access_url=invoice_access_url,
        zelle_email=tenant.zelle_email if tenant else None,
        zelle_phone=tenant.zelle_phone if tenant else None,
    )


def _build_invoice_email_html(
    customer, vehicle_info: str, invoice, order,
    labor_items: list, parts_items: list, invoice_access_url: str,
    tenant=None,
) -> str:
    shop_name = tenant.name if tenant else "Your Shop"
    shop_phone = tenant.phone if tenant else ""
    shop_email = tenant.email if tenant else ""

    # Line items HTML
    def item_rows_html(items, is_labor: bool) -> str:
        html = ""
        for item in items:
            if is_labor:
                hrs = float(item.get("hours", 0))
                rate = Decimal(str(item.get("hourly_rate", 0)))
                total = Decimal(str(item.get("total_cost", 0)))
                qty = f"{hrs:.1f} hr{'s' if hrs != 1 else ''}"
                desc = item.get("description", "")
            else:
                qty = str(item.get("quantity", 1))
                rate = Decimal(str(item.get("unit_price", 0)))
                total = Decimal(str(item.get("total_price", 0)))
                desc = item.get("name", "")
            html += f"""
            <tr>
              <td style="padding:6px 8px;color:#374151;border-bottom:1px solid #f3f4f6;">{desc}</td>
              <td style="padding:6px 8px;color:#6b7280;text-align:right;border-bottom:1px solid #f3f4f6;">{qty}</td>
              <td style="padding:6px 8px;color:#6b7280;text-align:right;border-bottom:1px solid #f3f4f6;">${rate:,.2f}</td>
              <td style="padding:6px 8px;color:#1f2937;font-weight:600;text-align:right;border-bottom:1px solid #f3f4f6;">${total:,.2f}</td>
            </tr>"""
        return html

    def section_header_html(label: str) -> str:
        return f"""
        <tr>
          <td colspan="4" style="padding:8px 8px 4px 8px;background:#f3f4f6;font-weight:700;font-size:12px;color:#374151;border-bottom:1px solid #e5e7eb;">{label}</td>
        </tr>"""

    items_html = ""
    if labor_items:
        items_html += section_header_html("Labor")
        items_html += item_rows_html(labor_items, is_labor=True)
    if parts_items:
        items_html += section_header_html("Parts")
        items_html += item_rows_html(parts_items, is_labor=False)

    # Fees
    if invoice.shop_supplies_amount and Decimal(str(invoice.shop_supplies_amount)) > 0:
        items_html += section_header_html("Fees")
        items_html += f"""
        <tr>
          <td style="padding:6px 8px;color:#374151;border-bottom:1px solid #f3f4f6;">Shop Supplies</td>
          <td style="padding:6px 8px;color:#6b7280;text-align:right;border-bottom:1px solid #f3f4f6;">1</td>
          <td style="padding:6px 8px;color:#6b7280;text-align:right;border-bottom:1px solid #f3f4f6;"></td>
          <td style="padding:6px 8px;color:#1f2937;font-weight:600;text-align:right;border-bottom:1px solid #f3f4f6;">${Decimal(str(invoice.shop_supplies_amount)):,.2f}</td>
        </tr>"""
    if invoice.service_fee_amount and Decimal(str(invoice.service_fee_amount)) > 0:
        items_html += f"""
        <tr>
          <td style="padding:6px 8px;color:#374151;border-bottom:1px solid #f3f4f6;">Processing Fee</td>
          <td style="padding:6px 8px;color:#6b7280;text-align:right;border-bottom:1px solid #f3f4f6;">1</td>
          <td style="padding:6px 8px;color:#6b7280;text-align:right;border-bottom:1px solid #f3f4f6;"></td>
          <td style="padding:6px 8px;color:#1f2937;font-weight:600;text-align:right;border-bottom:1px solid #f3f4f6;">${Decimal(str(invoice.service_fee_amount)):,.2f}</td>
        </tr>"""

    # Totals
    discount = Decimal(str(invoice.discount_amount or 0))
    tax = Decimal(str(invoice.tax_amount or 0))
    total = Decimal(str(invoice.total_amount))

    discount_row = ""
    if discount > 0:
        discount_row = f'<tr><td style="padding:4px 8px;text-align:right;color:#6b7280;" colspan="3">Discount</td><td style="padding:4px 8px;text-align:right;color:#16a34a;font-weight:600;">-${discount:,.2f}</td></tr>'

    due_str = ""
    if invoice.due_date:
        d = invoice.due_date
        due_str = d.strftime("%m/%d/%Y") if hasattr(d, "strftime") else str(d)

    shop_contact = ""
    if shop_phone:
        shop_contact += f" &nbsp;·&nbsp; {shop_phone}"
    if shop_email:
        shop_contact += f" &nbsp;·&nbsp; {shop_email}"

    return f"""
<div style="font-family:Arial,sans-serif;max-width:640px;margin:0 auto;background:#ffffff;">

  <!-- Header -->
  <div style="background:#1f2937;padding:24px 28px;border-radius:8px 8px 0 0;">
    <table width="100%" cellpadding="0" cellspacing="0">
      <tr>
        <td><span style="color:#ffffff;font-size:20px;font-weight:700;">INVOICE</span>
            <span style="color:#d97706;font-size:14px;font-weight:600;margin-left:10px;">{invoice.invoice_number}</span></td>
        <td align="right"><span style="color:#f3f4f6;font-size:18px;font-weight:700;">{shop_name}</span></td>
      </tr>
    </table>
  </div>

  <!-- Bill-to / Invoice info -->
  <div style="background:#f9fafb;padding:20px 28px;border-bottom:1px solid #e5e7eb;">
    <table width="100%" cellpadding="0" cellspacing="0">
      <tr>
        <td style="vertical-align:top;width:50%;">
          <p style="margin:0 0 2px 0;font-size:10px;font-weight:700;color:#9ca3af;text-transform:uppercase;letter-spacing:.5px;">Bill To</p>
          <p style="margin:0 0 2px 0;font-size:14px;font-weight:700;color:#1f2937;">{customer.first_name} {customer.last_name}</p>
          <p style="margin:0;font-size:12px;color:#6b7280;">{customer.email or ''}</p>
          <p style="margin:0;font-size:12px;color:#6b7280;">{customer.phone or ''}</p>
        </td>
        <td style="vertical-align:top;text-align:right;">
          <p style="margin:0 0 4px 0;font-size:12px;color:#6b7280;"><b>Vehicle:</b> {vehicle_info}</p>
          <p style="margin:0 0 4px 0;font-size:12px;color:#6b7280;"><b>Order #:</b> {order.order_number}</p>
          {"<p style='margin:0;font-size:12px;color:#6b7280;'><b>Due Date:</b> " + due_str + "</p>" if due_str else ""}
        </td>
      </tr>
    </table>
  </div>

  <!-- Line items table -->
  <div style="padding:20px 28px 0 28px;">
    <table width="100%" cellpadding="0" cellspacing="0" style="border:1px solid #e5e7eb;border-radius:6px;overflow:hidden;">
      <thead>
        <tr style="background:#1f2937;">
          <th style="padding:8px 8px;color:#ffffff;font-size:11px;text-align:left;font-weight:700;">Description</th>
          <th style="padding:8px 8px;color:#ffffff;font-size:11px;text-align:right;font-weight:700;">Qty/Hrs</th>
          <th style="padding:8px 8px;color:#ffffff;font-size:11px;text-align:right;font-weight:700;">Rate</th>
          <th style="padding:8px 8px;color:#ffffff;font-size:11px;text-align:right;font-weight:700;">Total</th>
        </tr>
      </thead>
      <tbody>
        {items_html}
      </tbody>
    </table>
  </div>

  <!-- Totals -->
  <div style="padding:12px 28px 20px 28px;">
    <table width="100%" cellpadding="0" cellspacing="0">
      <tr><td style="padding:4px 8px;text-align:right;color:#6b7280;" colspan="3">Subtotal</td><td style="padding:4px 8px;text-align:right;color:#374151;">${Decimal(str(invoice.subtotal)):,.2f}</td></tr>
      {discount_row}
      <tr><td style="padding:4px 8px;text-align:right;color:#6b7280;" colspan="3">Tax</td><td style="padding:4px 8px;text-align:right;color:#374151;">${tax:,.2f}</td></tr>
      <tr style="background:#1f2937;">
        <td style="padding:10px 8px;text-align:right;color:#ffffff;font-weight:700;font-size:15px;" colspan="3">TOTAL DUE</td>
        <td style="padding:10px 8px;text-align:right;color:#ffffff;font-weight:700;font-size:15px;">${total:,.2f}</td>
      </tr>
    </table>
  </div>

  <!-- CTA -->
  <div style="padding:0 28px 24px 28px;text-align:center;">
    <a href="{invoice_access_url}" style="display:inline-block;background:#d97706;color:#ffffff;padding:13px 32px;text-decoration:none;border-radius:8px;font-weight:700;font-size:15px;">
      View &amp; Pay Invoice
    </a>
    <p style="color:#9ca3af;font-size:11px;margin-top:10px;">A PDF copy of this invoice is attached for your records.</p>
  </div>

  <!-- Footer -->
  <div style="background:#f3f4f6;padding:16px 28px;border-radius:0 0 8px 8px;text-align:center;">
    <p style="margin:0;font-size:12px;color:#6b7280;">{shop_name}{shop_contact}</p>
    <p style="margin:6px 0 0 0;font-size:11px;color:#9ca3af;">Thank you for your business!</p>
    <p style="margin:10px 0 0 0;font-size:10px;color:#d1d5db;">Powered by DieselBridge Network</p>
  </div>

</div>
"""


class InvoiceCreate(BaseModel):
    repair_order_id: UUID
    due_date: Optional[date] = None
    discount_amount: Decimal = Decimal("0.00")


class InvoiceUpdate(BaseModel):
    due_date: Optional[date] = None
    notes: Optional[str] = None


class ResendInvoiceRequest(BaseModel):
    custom_email: Optional[str] = None


class InvoiceResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    repair_order_id: UUID
    invoice_number: str
    status: str
    is_internal: bool = False
    subtotal: Decimal
    shop_supplies_amount: Decimal = Decimal("0.00")
    service_fee_amount: Decimal = Decimal("0.00")
    tax_amount: Decimal
    discount_amount: Decimal
    total_amount: Decimal
    due_date: Optional[datetime]
    paid_at: Optional[datetime]
    notes: Optional[str]
    pending_zelle_confirmation: bool = False
    zelle_pending_submitted_at: Optional[datetime] = None
    zelle_pending_sender_email: Optional[str] = None
    zelle_pending_sender_phone: Optional[str] = None
    zelle_pending_last_reminder_at: Optional[datetime] = None
    zelle_pending_reminder_count: int = 0
    last_reminder_sent_at: Optional[datetime] = None
    reminder_count: int = 0
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class InvoiceDetailResponse(InvoiceResponse):
    order_number: str
    customer_name: str
    vehicle_info: str


def _require_staff(current_user: User) -> None:
    if current_user.role not in (
        UserRole.GARAGE_OWNER,
        UserRole.GARAGE_ADMIN,
        UserRole.RECEPTIONIST,
        UserRole.MECHANIC,
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions",
        )


async def generate_invoice_number(db: AsyncSession, tenant_id: UUID) -> str:
    """Generate unique invoice number using MAX approach."""
    from app.core.unique_id import generate_unique_number
    return await generate_unique_number(
        db=db,
        model_class=Invoice,
        number_column=Invoice.invoice_number,
        tenant_id=tenant_id,
        prefix="INV-",
    )


async def auto_create_invoice_for_order(
    db: AsyncSession,
    order: RepairOrder,
    tenant: Tenant,
) -> Optional[Invoice]:
    """Auto-create an invoice when a repair order is approved as completed.

    Returns the created Invoice, or None if one already exists.
    The order must have .customer and .vehicle relationships already loaded.
    """
    # Internal fleet repairs are settled at cost internally — never invoiced to a customer.
    if order.is_internal:
        return None

    existing_result = await db.execute(select(Invoice).where(Invoice.repair_order_id == order.id))
    if existing_result.scalar_one_or_none():
        return None

    # Capture relationships before any subsequent commits
    customer = order.customer
    vehicle = order.vehicle

    parts_total = get_order_parts_total(order)
    labor_total = get_order_labor_total(order)
    subtotal = parts_total + labor_total

    shop_supplies_rate = Decimal(str(tenant.shop_supplies_rate or 0)) / 100
    service_fee_rate = Decimal(str(tenant.service_fee_rate or 0)) / 100
    sales_tax_rate = Decimal(str(tenant.sales_tax_rate or 0)) / 100

    shop_supplies_amount = (labor_total * shop_supplies_rate).quantize(Decimal("0.01"))
    subtotal_with_supplies = subtotal + shop_supplies_amount
    service_fee_amount = (subtotal_with_supplies * service_fee_rate).quantize(Decimal("0.01"))
    taxable_amount = subtotal_with_supplies + service_fee_amount
    tax_amount = (taxable_amount * sales_tax_rate).quantize(Decimal("0.01"))
    total_amount = (taxable_amount + tax_amount).quantize(Decimal("0.01"))

    from app.core.unique_id import create_with_retry

    async def _create(invoice_number: str) -> Invoice:
        inv = Invoice(
            tenant_id=tenant.id,
            repair_order_id=order.id,
            invoice_number=invoice_number,
            status=InvoiceStatus.SENT,
            subtotal=subtotal,
            shop_supplies_amount=shop_supplies_amount,
            service_fee_amount=service_fee_amount,
            tax_amount=tax_amount,
            discount_amount=Decimal("0.00"),
            total_amount=total_amount,
            due_date=date.today(),
            paid_at=None,
            notes=None,
        )
        db.add(inv)
        order.status = RepairOrderStatus.INVOICED
        return inv

    invoice = await create_with_retry(
        db=db,
        create_fn=_create,
        generate_number_fn=lambda: generate_invoice_number(db, tenant.id),
        entity_name="invoice",
    )
    await db.refresh(invoice)
    await db.refresh(order)

    await broadcast_invoice_created(
        tenant_id=str(order.tenant_id),
        customer_id=str(order.customer_id),
        invoice_id=str(invoice.id),
        invoice_number=invoice.invoice_number,
        order_id=str(order.id),
        total_amount=str(invoice.total_amount),
    )
    await broadcast_repair_order_update(
        tenant_id=str(order.tenant_id),
        customer_id=str(order.customer_id),
        order_id=str(order.id),
        order_number=order.order_number,
        status=order.status.value,
        updated_at=order.updated_at.isoformat() if order.updated_at else None,
    )

    if customer and customer.email:
        vehicle_info = f"{vehicle.year or ''} {vehicle.make} {vehicle.model}".strip() if vehicle else "Vehicle"
        invoice_access_url = await generate_invoice_access_link(
            invoice=invoice,
            order=order,
            customer=customer,
            shop_name=tenant.name,
            shop_phone=tenant.phone,
            shop_email=tenant.email,
            shop_logo_url=tenant.logo_url,
        )
        labor_items, parts_items = await _load_line_items(db, order.id)
        email_html = _build_invoice_email_html(
            customer=customer,
            vehicle_info=vehicle_info,
            invoice=invoice,
            order=order,
            labor_items=labor_items,
            parts_items=parts_items,
            invoice_access_url=invoice_access_url,
            tenant=tenant,
        )
        try:
            pdf_bytes = _build_invoice_pdf_bytes(
                invoice=invoice, order=order, customer=customer,
                vehicle=vehicle, tenant=tenant,
                labor_items=labor_items, parts_items=parts_items,
                invoice_access_url=invoice_access_url,
            )
            attachments = [{"filename": f"Invoice-{invoice.invoice_number}.pdf", "content": pdf_bytes}]
        except Exception:
            attachments = None
        await send_email(
            db=db,
            tenant_id=str(order.tenant_id),
            to=customer.email,
            subject=f"Invoice {invoice.invoice_number} – {vehicle_info}",
            body=email_html,
            template_name="invoice_created",
            attachments=attachments,
        )

    return invoice


@router.post("", response_model=InvoiceResponse, status_code=status.HTTP_201_CREATED)
async def create_invoice(
    body: InvoiceCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    _require_staff(current_user)
    if not current_user.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User must be associated with a tenant",
        )
    result = await db.execute(
        select(RepairOrder)
        .options(selectinload(RepairOrder.customer), selectinload(RepairOrder.vehicle))
        .where(RepairOrder.id == body.repair_order_id)
    )
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Repair order not found",
        )
    if order.tenant_id != current_user.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )
    if order.is_internal:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Internal fleet repair orders are settled at cost and are not invoiced",
        )
    if order.status != RepairOrderStatus.COMPLETED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invoice can only be created for completed repair orders",
        )
    result = await db.execute(
        select(Invoice).where(Invoice.repair_order_id == body.repair_order_id)
    )
    existing = result.scalar_one_or_none()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="An invoice already exists for this repair order",
        )
    
    # Get tenant for tax/fee settings
    tenant_result = await db.execute(select(Tenant).where(Tenant.id == current_user.tenant_id))
    tenant = tenant_result.scalar_one_or_none()
    
    # Subtotal uses service/labor charges plus parts sell price.
    parts_total = get_order_parts_total(order)
    labor_total = get_order_labor_total(order)
    subtotal = parts_total + labor_total
    
    # Calculate fees based on tenant settings
    shop_supplies_rate = Decimal(str(tenant.shop_supplies_rate or 0)) / 100 if tenant else Decimal("0")
    service_fee_rate = Decimal(str(tenant.service_fee_rate or 0)) / 100 if tenant else Decimal("0")
    sales_tax_rate = Decimal(str(tenant.sales_tax_rate or 0)) / 100 if tenant else Decimal("0")
    
    # Shop supplies: percentage of labor
    shop_supplies_amount = (labor_total * shop_supplies_rate).quantize(Decimal("0.01"))
    
    # Subtotal after shop supplies
    subtotal_with_supplies = subtotal + shop_supplies_amount
    
    # Service fee: percentage of subtotal (after shop supplies)
    service_fee_amount = (subtotal_with_supplies * service_fee_rate).quantize(Decimal("0.01"))
    
    # Taxable amount (subtotal + shop supplies + service fee)
    taxable_amount = subtotal_with_supplies + service_fee_amount
    
    # Sales tax
    tax_amount = (taxable_amount * sales_tax_rate).quantize(Decimal("0.01"))

    requested_discount = (body.discount_amount or Decimal("0.00")).quantize(Decimal("0.01"))
    if requested_discount < 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="discount_amount must be greater than or equal to 0.00",
        )

    pre_discount_total = taxable_amount + tax_amount
    if requested_discount > pre_discount_total:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="discount_amount cannot exceed invoice total",
        )
    
    # Total
    total_amount = (pre_discount_total - requested_discount).quantize(Decimal("0.01"))
    
    # Default due date to today if not specified
    due_date = body.due_date if body.due_date else date.today()
    
    # Use retry wrapper to handle rare race conditions on invoice number
    from app.core.unique_id import create_with_retry
    
    async def create_invoice_with_number(invoice_number: str) -> Invoice:
        invoice = Invoice(
            tenant_id=current_user.tenant_id,
            repair_order_id=order.id,
            invoice_number=invoice_number,
            status=InvoiceStatus.SENT,
            subtotal=subtotal,
            shop_supplies_amount=shop_supplies_amount,
            service_fee_amount=service_fee_amount,
            tax_amount=tax_amount,
            discount_amount=requested_discount,
            total_amount=total_amount,
            due_date=due_date,
            paid_at=None,
            notes=None,
        )
        db.add(invoice)
        order.status = RepairOrderStatus.INVOICED
        # Don't commit here - create_with_retry uses savepoints and handles commit
        return invoice
    
    invoice = await create_with_retry(
        db=db,
        create_fn=create_invoice_with_number,
        generate_number_fn=lambda: generate_invoice_number(db, current_user.tenant_id),
        entity_name="invoice",
    )
    await db.refresh(invoice)
    await db.refresh(order)
    
    # Broadcast WebSocket updates
    await broadcast_invoice_created(
        tenant_id=str(order.tenant_id),
        customer_id=str(order.customer_id),
        invoice_id=str(invoice.id),
        invoice_number=invoice.invoice_number,
        order_id=str(order.id),
        total_amount=str(invoice.total_amount),
    )
    await broadcast_repair_order_update(
        tenant_id=str(order.tenant_id),
        customer_id=str(order.customer_id),
        order_id=str(order.id),
        order_number=order.order_number,
        status=order.status.value,
        updated_at=order.updated_at.isoformat() if order.updated_at else None,
    )
    
    # Send invoice email to customer
    customer = order.customer
    vehicle = order.vehicle
    if customer and customer.email:
        vehicle_info = f"{vehicle.year or ''} {vehicle.make} {vehicle.model}".strip() if vehicle else "Vehicle"
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

        email_html = _build_invoice_email_html(
            customer=customer,
            vehicle_info=vehicle_info,
            invoice=invoice,
            order=order,
            labor_items=labor_items,
            parts_items=parts_items,
            invoice_access_url=invoice_access_url,
            tenant=tenant,
        )

        try:
            pdf_bytes = _build_invoice_pdf_bytes(
                invoice=invoice, order=order, customer=customer,
                vehicle=vehicle, tenant=tenant,
                labor_items=labor_items, parts_items=parts_items,
                invoice_access_url=invoice_access_url,
            )
            attachments = [{"filename": f"Invoice-{invoice.invoice_number}.pdf", "content": pdf_bytes}]
        except Exception:
            attachments = None

        await send_email(
            db=db,
            tenant_id=str(order.tenant_id),
            to=customer.email,
            subject=f"Invoice {invoice.invoice_number} – {vehicle_info}",
            body=email_html,
            template_name="invoice_created",
            attachments=attachments,
        )
    
    return InvoiceResponse.model_validate(invoice)


@router.get("", response_model=List[InvoiceResponse])
async def list_invoices(
    status_filter: Optional[str] = Query(None),
    repair_order_id: Optional[UUID] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
    paginated: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    query = select(Invoice).join(RepairOrder, Invoice.repair_order_id == RepairOrder.id)
    count_query = select(func.count(Invoice.id)).join(RepairOrder, Invoice.repair_order_id == RepairOrder.id)
    if current_user.role == UserRole.CUSTOMER:
        if not current_user.customer_id:
            return paginated_or_list([], 0, skip, limit, paginated)
        query = query.where(RepairOrder.customer_id == current_user.customer_id)
        count_query = count_query.where(RepairOrder.customer_id == current_user.customer_id)
    else:
        if not current_user.tenant_id:
            return paginated_or_list([], 0, skip, limit, paginated)
        query = query.where(Invoice.tenant_id == current_user.tenant_id)
        count_query = count_query.where(Invoice.tenant_id == current_user.tenant_id)
    if status_filter:
        query = query.where(Invoice.status == status_filter)
        count_query = count_query.where(Invoice.status == status_filter)
    if repair_order_id:
        query = query.where(Invoice.repair_order_id == repair_order_id)
        count_query = count_query.where(Invoice.repair_order_id == repair_order_id)

    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    query = query.order_by(Invoice.created_at.desc()).offset(skip).limit(limit)

    result = await db.execute(query)
    invoices = result.scalars().all()
    items = [InvoiceResponse.model_validate(inv) for inv in invoices]
    return paginated_or_list(items, total, skip, limit, paginated)


@router.get("/{invoice_id}", response_model=InvoiceDetailResponse)
async def get_invoice(
    invoice_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    result = await db.execute(
        select(Invoice, RepairOrder, Customer, Vehicle)
        .join(RepairOrder, Invoice.repair_order_id == RepairOrder.id)
        .join(Customer, RepairOrder.customer_id == Customer.id)
        .join(Vehicle, RepairOrder.vehicle_id == Vehicle.id)
        .where(Invoice.id == invoice_id)
    )
    row = result.one_or_none()
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invoice not found",
        )
    inv, order, customer, vehicle = row
    if current_user.role == UserRole.CUSTOMER:
        if not current_user.customer_id or current_user.customer_id != order.customer_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied",
            )
    elif current_user.tenant_id != inv.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )
    vehicle_info = f"{vehicle.year or ''} {vehicle.make} {vehicle.model}".strip()
    customer_name = f"{customer.first_name} {customer.last_name}"
    return InvoiceDetailResponse(
        **InvoiceResponse.model_validate(inv).model_dump(),
        order_number=order.order_number,
        customer_name=customer_name,
        vehicle_info=vehicle_info,
    )


@router.patch("/{invoice_id}", response_model=InvoiceResponse)
async def update_invoice(
    invoice_id: UUID,
    body: InvoiceUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Update invoice due date or notes"""
    _require_staff(current_user)
    
    result = await db.execute(select(Invoice).where(Invoice.id == invoice_id))
    invoice = result.scalar_one_or_none()
    
    if not invoice:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found")
    
    if current_user.tenant_id != invoice.tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    
    if invoice.status == InvoiceStatus.PAID:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot modify a paid invoice")
    
    if body.due_date is not None:
        invoice.due_date = body.due_date
    if body.notes is not None:
        invoice.notes = body.notes
    
    await db.commit()
    await db.refresh(invoice)
    
    return InvoiceResponse.model_validate(invoice)


@router.delete("/{invoice_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_invoice(
    invoice_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Delete an invoice (only if not paid)"""
    _require_staff(current_user)
    
    result = await db.execute(
        select(Invoice)
        .options(selectinload(Invoice.repair_order))
        .where(Invoice.id == invoice_id)
    )
    invoice = result.scalar_one_or_none()
    
    if not invoice:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found")
    
    if current_user.tenant_id != invoice.tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    
    if invoice.status == InvoiceStatus.PAID:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot delete a paid invoice")
    
    # Revert repair order status to completed
    order = invoice.repair_order
    order.status = RepairOrderStatus.COMPLETED
    
    await db.delete(invoice)
    await db.commit()

    await db.refresh(order)

    # Broadcast status rollback so active views update in real time.
    await broadcast_repair_order_update(
        tenant_id=str(order.tenant_id),
        customer_id=str(order.customer_id),
        order_id=str(order.id),
        order_number=order.order_number,
        status=order.status.value,
        updated_at=order.updated_at.isoformat() if order.updated_at else None,
    )


@router.post("/{invoice_id}/resend")
async def resend_invoice(
    invoice_id: UUID,
    body: ResendInvoiceRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Resend invoice email, optionally to a custom email address"""
    _require_staff(current_user)
    
    result = await db.execute(
        select(Invoice, RepairOrder, Customer, Vehicle)
        .join(RepairOrder, Invoice.repair_order_id == RepairOrder.id)
        .join(Customer, RepairOrder.customer_id == Customer.id)
        .join(Vehicle, RepairOrder.vehicle_id == Vehicle.id)
        .where(Invoice.id == invoice_id)
    )
    row = result.one_or_none()
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invoice not found",
        )
    
    invoice, order, customer, vehicle = row
    
    if current_user.tenant_id != invoice.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )
    
    # Use custom email if provided, otherwise use customer's email
    to_email = body.custom_email if body.custom_email else customer.email
    if not to_email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No email address available",
        )
    
    vehicle_info = f"{vehicle.year or ''} {vehicle.make} {vehicle.model}".strip()
    tenant_result = await db.execute(select(Tenant).where(Tenant.id == invoice.tenant_id))
    tenant = tenant_result.scalar_one_or_none()
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

    email_html = _build_invoice_email_html(
        customer=customer,
        vehicle_info=vehicle_info,
        invoice=invoice,
        order=order,
        labor_items=labor_items,
        parts_items=parts_items,
        invoice_access_url=invoice_access_url,
        tenant=tenant,
    )

    try:
        pdf_bytes = _build_invoice_pdf_bytes(
            invoice=invoice, order=order, customer=customer,
            vehicle=vehicle, tenant=tenant,
            labor_items=labor_items, parts_items=parts_items,
            invoice_access_url=invoice_access_url,
        )
        attachments = [{"filename": f"Invoice-{invoice.invoice_number}.pdf", "content": pdf_bytes}]
    except Exception:
        attachments = None

    await send_email(
        db=db,
        tenant_id=str(invoice.tenant_id),
        to=to_email,
        subject=f"Invoice {invoice.invoice_number} – {vehicle_info}",
        body=email_html,
        template_name="invoice_resend",
        attachments=attachments,
    )

    return {"status": "success", "message": f"Invoice sent to {to_email}"}


@router.get("/{invoice_id}/pdf")
async def download_invoice_pdf(
    invoice_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Download invoice as PDF (staff + customer)."""
    result = await db.execute(
        select(Invoice, RepairOrder, Customer, Vehicle)
        .join(RepairOrder, Invoice.repair_order_id == RepairOrder.id)
        .join(Customer, RepairOrder.customer_id == Customer.id)
        .join(Vehicle, RepairOrder.vehicle_id == Vehicle.id)
        .where(Invoice.id == invoice_id)
    )
    row = result.one_or_none()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found")

    inv, order, customer, vehicle = row

    if current_user.role == UserRole.CUSTOMER:
        if not current_user.customer_id or current_user.customer_id != order.customer_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    elif current_user.tenant_id != inv.tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    tenant_result = await db.execute(select(Tenant).where(Tenant.id == inv.tenant_id))
    tenant = tenant_result.scalar_one_or_none()

    labor_items, parts_items = await _load_line_items(db, order.id)

    pdf_bytes = _build_invoice_pdf_bytes(
        invoice=inv, order=order, customer=customer,
        vehicle=vehicle, tenant=tenant,
        labor_items=labor_items, parts_items=parts_items,
        invoice_access_url=None,
    )

    filename = f"Invoice-{inv.invoice_number}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
