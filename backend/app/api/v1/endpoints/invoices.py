from datetime import datetime
from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func
from pydantic import BaseModel
from decimal import Decimal

from app.core.dependencies import get_db, get_current_active_user
from app.db.models.user import User, UserRole
from app.db.models.repair_order import RepairOrder, RepairOrderStatus
from app.db.models.invoice import Invoice, InvoiceStatus
from app.db.models.customer import Customer
from app.db.models.vehicle import Vehicle

router = APIRouter()


class InvoiceCreate(BaseModel):
    repair_order_id: UUID


class InvoiceResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    repair_order_id: UUID
    invoice_number: str
    status: str
    subtotal: Decimal
    tax_amount: Decimal
    discount_amount: Decimal
    total_amount: Decimal
    due_date: Optional[datetime]
    paid_at: Optional[datetime]
    notes: Optional[str]
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
        UserRole.SUPER_ADMIN,
        UserRole.GARAGE_ADMIN,
        UserRole.RECEPTIONIST,
        UserRole.MECHANIC,
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions",
        )


async def generate_invoice_number(db: AsyncSession, tenant_id: UUID) -> str:
    result = await db.execute(
        select(func.count(Invoice.id)).where(Invoice.tenant_id == tenant_id)
    )
    count = result.scalar() or 0
    return f"INV-{str(tenant_id).replace('-', '').upper()[:8]}-{count + 1:06d}"


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
        select(RepairOrder).where(RepairOrder.id == body.repair_order_id)
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
    invoice_number = await generate_invoice_number(db, current_user.tenant_id)
    subtotal = order.total_cost
    total_amount = subtotal
    invoice = Invoice(
        tenant_id=current_user.tenant_id,
        repair_order_id=order.id,
        invoice_number=invoice_number,
        status=InvoiceStatus.SENT,
        subtotal=subtotal,
        tax_amount=Decimal("0.00"),
        discount_amount=Decimal("0.00"),
        total_amount=total_amount,
        due_date=None,
        paid_at=None,
        notes=None,
    )
    db.add(invoice)
    order.status = RepairOrderStatus.INVOICED
    await db.commit()
    await db.refresh(invoice)
    return InvoiceResponse.model_validate(invoice)


@router.get("", response_model=List[InvoiceResponse])
async def list_invoices(
    status_filter: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    query = select(Invoice).join(RepairOrder, Invoice.repair_order_id == RepairOrder.id)
    if current_user.role == UserRole.CUSTOMER:
        if not current_user.customer_id:
            return []
        query = query.where(RepairOrder.customer_id == current_user.customer_id)
    else:
        if not current_user.tenant_id:
            return []
        query = query.where(Invoice.tenant_id == current_user.tenant_id)
    if status_filter:
        query = query.where(Invoice.status == status_filter)
    query = query.order_by(Invoice.created_at.desc())
    result = await db.execute(query)
    invoices = result.scalars().all()
    return [InvoiceResponse.model_validate(inv) for inv in invoices]


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
