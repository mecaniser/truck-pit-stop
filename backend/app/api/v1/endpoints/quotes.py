import json
import secrets
from datetime import datetime
from typing import Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from pydantic import BaseModel
from decimal import Decimal

from app.core.dependencies import get_db, get_current_active_user
from app.core.config import settings
from app.db.models.user import User, UserRole
from app.db.models.repair_order import RepairOrder, RepairOrderStatus
from app.db.models.quote import Quote
from app.db.models.customer import Customer
from app.db.models.vehicle import Vehicle
from app.services.email_service import send_email

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
    is_declined: bool = False
    decline_notes: Optional[str] = None
    sent_to_customer: bool = False
    sent_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class DeclineQuoteRequest(BaseModel):
    notes: Optional[str] = None


class QuoteDetailResponse(BaseModel):
    """Extended quote response with repair order and vehicle details for magic link"""
    quote: QuoteResponse
    order_number: str
    order_description: Optional[str]
    vehicle_year: Optional[int]
    vehicle_make: Optional[str]
    vehicle_model: Optional[str]
    vehicle_vin: Optional[str]
    customer_first_name: str
    services: list[dict] = []


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
    
    # Calculate total: service prices (from internal_notes) are all-in (include parts + labor)
    # If services selected, total = service total only (parts are for inventory tracking, not added)
    # If no services, total = backend total_cost (parts + labor)
    service_total = Decimal("0")
    if order.internal_notes:
        try:
            notes_data = json.loads(order.internal_notes)
            selected_services = notes_data.get("selected_services", [])
            for svc in selected_services:
                service_total += Decimal(str(svc.get("base_price", "0")))
        except (json.JSONDecodeError, TypeError, ValueError):
            pass
    
    # If services selected, use service total; otherwise use backend total
    total_amount = service_total if service_total > 0 else order.total_cost
    
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


@router.put("/{quote_id}", response_model=QuoteResponse)
async def update_quote(
    quote_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Recalculate and update quote total based on current repair order state"""
    _require_staff(current_user)
    
    result = await db.execute(
        select(Quote).where(Quote.id == quote_id)
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
    
    if current_user.tenant_id != order.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )
    
    if quote.is_approved:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot update an approved quote",
        )
    
    # Recalculate total using same logic as create
    service_total = Decimal("0")
    if order.internal_notes:
        try:
            notes_data = json.loads(order.internal_notes)
            selected_services = notes_data.get("selected_services", [])
            for svc in selected_services:
                service_total += Decimal(str(svc.get("base_price", "0")))
        except (json.JSONDecodeError, TypeError, ValueError):
            pass
    
    quote.total_amount = service_total if service_total > 0 else order.total_cost
    await db.commit()
    await db.refresh(quote)
    return QuoteResponse.model_validate(quote)


@router.post("/{quote_id}/send", response_model=QuoteResponse)
async def send_quote_to_customer(
    quote_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Send quote to customer via email for approval"""
    _require_staff(current_user)
    
    result = await db.execute(
        select(Quote).where(Quote.id == quote_id)
    )
    quote = result.scalar_one_or_none()
    if not quote:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Quote not found",
        )
    
    result = await db.execute(
        select(RepairOrder)
        .where(RepairOrder.id == quote.repair_order_id)
        .options(selectinload(RepairOrder.customer), selectinload(RepairOrder.vehicle))
    )
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Repair order not found",
        )
    
    if current_user.tenant_id != order.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )
    
    customer = order.customer
    if not customer or not customer.email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Customer email not found",
        )
    
    # Generate magic link token
    quote.approval_token = secrets.token_urlsafe(48)
    
    # Parse services from internal_notes for email
    services_html = ""
    if order.internal_notes:
        try:
            notes_data = json.loads(order.internal_notes)
            selected_services = notes_data.get("selected_services", [])
            if selected_services:
                services_html = '<div style="margin: 15px 0;"><strong>Services:</strong><ul style="margin: 10px 0; padding-left: 20px;">'
                for svc in selected_services:
                    svc_name = svc.get("name", "Service")
                    svc_price = Decimal(str(svc.get("base_price", "0")))
                    services_html += f'<li style="margin: 5px 0;">{svc_name} - ${svc_price:,.2f}</li>'
                services_html += '</ul></div>'
        except (json.JSONDecodeError, TypeError, ValueError):
            pass
    
    # Build vehicle info
    vehicle = order.vehicle
    vehicle_info = ""
    if vehicle:
        vehicle_info = f"{vehicle.year} {vehicle.make} {vehicle.model}"
        if vehicle.vin:
            vehicle_info += f" (VIN: {vehicle.vin[-6:]})"
    
    # Build magic link URL
    approval_url = f"{settings.FRONTEND_URL}/quote/{quote.approval_token}"
    
    html_body = f"""
    <html>
    <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
        <div style="text-align: center; margin-bottom: 30px;">
            <h1 style="color: #d97706; margin: 0;">🔧 Truck Pit Stop</h1>
        </div>
        
        <h2 style="color: #333;">Quote Ready for Your Approval</h2>
        <p>Hi {customer.first_name},</p>
        <p>Your quote for repair order <strong>{order.order_number}</strong> is ready for review.</p>
        
        <div style="background: #f9fafb; border-radius: 8px; padding: 20px; margin: 20px 0; border: 1px solid #e5e7eb;">
            <p style="margin: 0 0 10px 0;"><strong>Quote #:</strong> {quote.quote_number}</p>
            {f'<p style="margin: 0 0 10px 0;"><strong>Vehicle:</strong> {vehicle_info}</p>' if vehicle_info else ''}
            <p style="margin: 0 0 10px 0;"><strong>Description:</strong> {order.description or 'General Repair'}</p>
            {services_html}
            <hr style="border: none; border-top: 1px solid #e5e7eb; margin: 15px 0;">
            <p style="margin: 0; font-size: 28px; color: #d97706; text-align: center;"><strong>Total: ${quote.total_amount:,.2f}</strong></p>
        </div>
        
        <p style="text-align: center; margin: 30px 0;">
            <a href="{approval_url}" 
               style="background-color: #16a34a; color: white; padding: 14px 32px; text-decoration: none; border-radius: 6px; display: inline-block; font-weight: bold; margin-right: 10px;">
                ✓ Approve Quote
            </a>
        </p>
        
        <p style="text-align: center; color: #666; font-size: 14px;">
            Click the button above to review the full quote details and approve or decline.
        </p>
        
        <hr style="border: none; border-top: 1px solid #e5e7eb; margin: 30px 0;">
        
        <p style="color: #666; font-size: 12px; text-align: center;">
            If you have any questions, please contact us directly.<br>
            This link expires in 7 days.
        </p>
    </body>
    </html>
    """
    
    # Mark as sent
    quote.sent_to_customer = True
    quote.sent_at = datetime.utcnow()
    
    await db.commit()
    await db.refresh(quote)
    
    await send_email(
        db=db,
        tenant_id=str(current_user.tenant_id),
        to=customer.email,
        subject=f"Quote {quote.quote_number} Ready for Approval - Truck Pit Stop",
        body=html_body,
        template_name="quote_approval",
    )
    
    return QuoteResponse.model_validate(quote)


@router.post("/{quote_id}/approve", response_model=QuoteResponse)
async def approve_quote(
    quote_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Approve a quote - typically called by customer from portal"""
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
    quote.is_declined = False
    quote.decline_notes = None
    order.status = RepairOrderStatus.APPROVED
    await db.commit()
    await db.refresh(quote)
    return QuoteResponse.model_validate(quote)


@router.post("/{quote_id}/decline", response_model=QuoteResponse)
async def decline_quote(
    quote_id: UUID,
    body: DeclineQuoteRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Decline a quote with optional notes"""
    result = await db.execute(
        select(Quote).where(Quote.id == quote_id)
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
    # Check access
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
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot decline an already approved quote",
        )
    
    quote.is_declined = True
    quote.decline_notes = body.notes
    order.status = RepairOrderStatus.DRAFT  # Back to draft for revision
    await db.commit()
    await db.refresh(quote)
    return QuoteResponse.model_validate(quote)


# ============ Magic Link Endpoints (no auth required) ============

@router.get("/token/{token}", response_model=QuoteDetailResponse)
async def get_quote_by_token(
    token: str,
    db: AsyncSession = Depends(get_db),
):
    """Get quote details by magic link token - no auth required"""
    result = await db.execute(
        select(Quote).where(Quote.approval_token == token)
    )
    quote = result.scalar_one_or_none()
    if not quote:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Quote not found or link expired",
        )
    
    result = await db.execute(
        select(RepairOrder)
        .where(RepairOrder.id == quote.repair_order_id)
        .options(selectinload(RepairOrder.customer), selectinload(RepairOrder.vehicle))
    )
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Repair order not found",
        )
    
    # Parse services
    services = []
    if order.internal_notes:
        try:
            notes_data = json.loads(order.internal_notes)
            services = notes_data.get("selected_services", [])
        except (json.JSONDecodeError, TypeError, ValueError):
            pass
    
    vehicle = order.vehicle
    customer = order.customer
    
    return QuoteDetailResponse(
        quote=QuoteResponse.model_validate(quote),
        order_number=order.order_number,
        order_description=order.description,
        vehicle_year=vehicle.year if vehicle else None,
        vehicle_make=vehicle.make if vehicle else None,
        vehicle_model=vehicle.model if vehicle else None,
        vehicle_vin=vehicle.vin if vehicle else None,
        customer_first_name=customer.first_name if customer else "Customer",
        services=services,
    )


@router.post("/token/{token}/approve", response_model=QuoteResponse)
async def approve_quote_by_token(
    token: str,
    db: AsyncSession = Depends(get_db),
):
    """Approve quote via magic link - no auth required"""
    result = await db.execute(
        select(Quote).where(Quote.approval_token == token)
    )
    quote = result.scalar_one_or_none()
    if not quote:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Quote not found or link expired",
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
    
    if quote.is_declined:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This quote was declined. Please contact us for a revised quote.",
        )
    
    if quote.is_approved:
        return QuoteResponse.model_validate(quote)
    
    quote.is_approved = True
    quote.is_declined = False
    order.status = RepairOrderStatus.APPROVED
    # Invalidate token after use for security
    quote.approval_token = None
    await db.commit()
    await db.refresh(quote)
    return QuoteResponse.model_validate(quote)


@router.post("/token/{token}/decline", response_model=QuoteResponse)
async def decline_quote_by_token(
    token: str,
    body: DeclineQuoteRequest,
    db: AsyncSession = Depends(get_db),
):
    """Decline quote via magic link - no auth required"""
    result = await db.execute(
        select(Quote).where(Quote.approval_token == token)
    )
    quote = result.scalar_one_or_none()
    if not quote:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Quote not found or link expired",
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
    
    if quote.is_approved:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot decline an already approved quote",
        )
    
    quote.is_declined = True
    quote.decline_notes = body.notes
    order.status = RepairOrderStatus.DRAFT
    # Keep token valid so customer can change their mind
    await db.commit()
    await db.refresh(quote)
    return QuoteResponse.model_validate(quote)
