from datetime import datetime, date
from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status, Query
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
from app.services.pricing import get_order_labor_total, get_order_parts_total
from app.services.email_service import send_email
from app.services.invoice_access_service import generate_invoice_access_link
from sqlalchemy.orm import selectinload
from app.core.websocket import broadcast_invoice_created, broadcast_repair_order_update

router = APIRouter()


class InvoiceCreate(BaseModel):
    repair_order_id: UUID
    due_date: Optional[date] = None


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
    subtotal: Decimal
    shop_supplies_amount: Decimal = Decimal("0.00")
    service_fee_amount: Decimal = Decimal("0.00")
    tax_amount: Decimal
    discount_amount: Decimal
    total_amount: Decimal
    due_date: Optional[datetime]
    paid_at: Optional[datetime]
    notes: Optional[str]
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
    
    # Total
    total_amount = taxable_amount + tax_amount
    
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
            discount_amount=Decimal("0.00"),
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
        invoice_access_url = await generate_invoice_access_link(invoice=invoice, order=order, customer=customer)
        
        # Build fee breakdown lines
        fee_lines = []
        fee_lines.append(f'<p style="margin: 0 0 5px 0;">Subtotal: ${invoice.subtotal:.2f}</p>')
        if invoice.shop_supplies_amount > 0:
            fee_lines.append(f'<p style="margin: 0 0 5px 0;">Shop Supplies: ${invoice.shop_supplies_amount:.2f}</p>')
        if invoice.service_fee_amount > 0:
            fee_lines.append(f'<p style="margin: 0 0 5px 0;">Service Fee: ${invoice.service_fee_amount:.2f}</p>')
        if invoice.tax_amount > 0:
            fee_lines.append(f'<p style="margin: 0 0 5px 0;">Tax: ${invoice.tax_amount:.2f}</p>')
        fee_breakdown = "\n                ".join(fee_lines)
        
        email_html = f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
            <h2 style="color: #1f2937;">Invoice Ready for Payment</h2>
            <p>Hi {customer.first_name},</p>
            <p>Your invoice for the repair work on your <strong>{vehicle_info}</strong> is ready.</p>
            
            <div style="background: #f3f4f6; border-radius: 8px; padding: 20px; margin: 20px 0;">
                <p style="margin: 0 0 10px 0;"><strong>Invoice #:</strong> {invoice.invoice_number}</p>
                <p style="margin: 0 0 10px 0;"><strong>Order #:</strong> {order.order_number}</p>
                <div style="border-top: 1px solid #e5e7eb; margin: 15px 0; padding-top: 15px;">
                {fee_breakdown}
                </div>
                <p style="margin: 15px 0 0 0; font-size: 24px; color: #1f2937; border-top: 1px solid #e5e7eb; padding-top: 15px;"><strong>Total: ${invoice.total_amount:.2f}</strong></p>
            </div>
            
            <p>You can view and pay your invoice instantly:</p>
            
            <a href="{invoice_access_url}" style="display: inline-block; background: #f59e0b; color: white; padding: 12px 24px; text-decoration: none; border-radius: 8px; font-weight: bold; margin: 10px 0;">
                View Invoice & Pay
            </a>
            
            <p style="color: #6b7280; font-size: 14px; margin-top: 30px;">
                If you have any questions about your invoice, please contact us.
            </p>
            
            <p>Thank you for your business!</p>
        </div>
        """
        
        await send_email(
            db=db,
            tenant_id=str(order.tenant_id),
            to=customer.email,
            subject=f"Invoice {invoice.invoice_number} - Payment Ready",
            body=email_html,
            template_name="invoice_created",
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
    invoice_access_url = await generate_invoice_access_link(invoice=invoice, order=order, customer=customer)
    
    email_html = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
        <h2 style="color: #1f2937;">Invoice Ready for Payment</h2>
        <p>Hi {customer.first_name},</p>
        <p>Your invoice for the repair work on your <strong>{vehicle_info}</strong> is ready.</p>
        
        <div style="background: #f3f4f6; border-radius: 8px; padding: 20px; margin: 20px 0;">
            <p style="margin: 0 0 10px 0;"><strong>Invoice #:</strong> {invoice.invoice_number}</p>
            <p style="margin: 0 0 10px 0;"><strong>Order #:</strong> {order.order_number}</p>
            <p style="margin: 0; font-size: 24px; color: #1f2937;"><strong>Total: ${invoice.total_amount:.2f}</strong></p>
        </div>
        
        <p>You can view and pay your invoice instantly:</p>
        
        <a href="{invoice_access_url}" style="display: inline-block; background: #f59e0b; color: white; padding: 12px 24px; text-decoration: none; border-radius: 8px; font-weight: bold; margin: 10px 0;">
            View Invoice & Pay
        </a>
        
        <p style="color: #6b7280; font-size: 14px; margin-top: 30px;">
            If you have any questions about your invoice, please contact us.
        </p>
        
        <p>Thank you for your business!</p>
    </div>
    """
    
    await send_email(
        db=db,
        tenant_id=str(invoice.tenant_id),
        to=to_email,
        subject=f"Invoice {invoice.invoice_number} - Payment Ready",
        body=email_html,
        template_name="invoice_resend",
    )
    
    return {"status": "success", "message": f"Invoice sent to {to_email}"}
