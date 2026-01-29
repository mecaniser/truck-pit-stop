from datetime import datetime
from typing import Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from pydantic import BaseModel
from decimal import Decimal

from app.core.dependencies import get_db, get_current_active_user
from app.db.models.user import User, UserRole
from app.db.models.repair_order import RepairOrder, RepairOrderStatus
from app.db.models.quote import Quote

router = APIRouter()


class QuoteCreate(BaseModel):
    repair_order_id: UUID
    notes: Optional[str] = None
    expires_at: Optional[datetime] = None


class QuoteResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    repair_order_id: UUID
    quote_number: str
    total_amount: Decimal
    notes: Optional[str]
    expires_at: Optional[datetime]
    is_approved: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


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


async def generate_quote_number(db: AsyncSession, tenant_id: UUID) -> str:
    result = await db.execute(
        select(func.count(Quote.id)).where(Quote.tenant_id == tenant_id)
    )
    count = result.scalar() or 0
    return f"Q-{str(tenant_id).replace('-', '').upper()[:8]}-{count + 1:06d}"


@router.post("", response_model=QuoteResponse, status_code=status.HTTP_201_CREATED)
async def create_quote(
    body: QuoteCreate,
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
    if order.status not in (RepairOrderStatus.DRAFT, RepairOrderStatus.QUOTED):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Quote can only be created for draft or quoted repair orders",
        )
    result = await db.execute(
        select(Quote).where(Quote.repair_order_id == body.repair_order_id)
    )
    existing = result.scalar_one_or_none()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A quote already exists for this repair order",
        )
    quote_number = await generate_quote_number(db, current_user.tenant_id)
    total_amount = order.total_cost
    quote = Quote(
        tenant_id=current_user.tenant_id,
        repair_order_id=order.id,
        quote_number=quote_number,
        total_amount=total_amount,
        notes=body.notes,
        expires_at=body.expires_at,
        is_approved=False,
    )
    db.add(quote)
    order.status = RepairOrderStatus.QUOTED
    await db.commit()
    await db.refresh(quote)
    return QuoteResponse.model_validate(quote)


@router.get("", response_model=Optional[QuoteResponse])
async def get_quote_by_repair_order(
    repair_order_id: UUID = Query(..., description="Repair order ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    result = await db.execute(
        select(RepairOrder).where(RepairOrder.id == repair_order_id)
    )
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Repair order not found",
        )
    if current_user.role == UserRole.CUSTOMER:
        if not current_user.customer_id or current_user.customer_id != order.customer_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied",
            )
    elif current_user.tenant_id != order.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )
    result = await db.execute(
        select(Quote).where(Quote.repair_order_id == repair_order_id)
    )
    quote = result.scalar_one_or_none()
    if not quote:
        return None
    return QuoteResponse.model_validate(quote)


@router.post("/{quote_id}/approve", response_model=QuoteResponse)
async def approve_quote(
    quote_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    result = await db.execute(
        select(Quote).where(Quote.id == quote_id).options()
    )
    quote = result.scalar_one_or_none()
    if not quote:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Quote not found",
        )
    result = await db.execute(
        select(RepairOrder).where(RepairOrder.id == quote.repair_order_id)
    )
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Repair order not found",
        )
    if current_user.role == UserRole.CUSTOMER:
        if not current_user.customer_id or current_user.customer_id != order.customer_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied",
            )
    else:
        if current_user.tenant_id != order.tenant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied",
            )
    if quote.is_approved:
        return QuoteResponse.model_validate(quote)
    quote.is_approved = True
    order.status = RepairOrderStatus.APPROVED
    await db.commit()
    await db.refresh(quote)
    return QuoteResponse.model_validate(quote)
