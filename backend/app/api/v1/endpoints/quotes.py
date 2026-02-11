import json
import secrets
from datetime import datetime
from typing import Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from sqlalchemy.orm import selectinload
from pydantic import BaseModel
from decimal import Decimal

from app.core.dependencies import get_db, get_current_active_user
from app.core.config import settings
from app.core.rate_limit import limiter
from app.db.models.user import User, UserRole
from app.db.models.repair_order import RepairOrder, RepairOrderStatus
from app.db.models.quote import Quote
from app.db.models.customer import Customer
from app.db.models.vehicle import Vehicle
from app.db.models.inventory import PartsUsage
from app.services.email_service import send_email
from app.services.twilio_service import send_sms
from app.services.pricing import (
    get_order_labor_total,
    get_order_parts_total,
    get_order_subtotal,
    get_selected_services_total,
)
from app.core.websocket import broadcast_quote_event, broadcast_repair_order_update, WSEventType

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
    parts: list[dict] = []
    labor_total: Decimal = Decimal("0.00")
    parts_total: Decimal = Decimal("0.00")


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


async def generate_quote_number(db: AsyncSession, tenant_id: UUID) -> str:
    """Generate unique quote number using MAX approach."""
    from app.core.unique_id import generate_unique_number
    return await generate_unique_number(
        db=db,
        model_class=Quote,
        number_column=Quote.quote_number,
        tenant_id=tenant_id,
        prefix="Q-",
    )


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
    
    # Quote subtotal is labor/services + parts.
    total_amount = get_order_subtotal(order)
    
    # Use retry wrapper to handle rare race conditions on quote number
    from app.core.unique_id import create_with_retry
    
    async def create_quote_with_number(quote_number: str) -> Quote:
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
        # Don't commit here - create_with_retry uses savepoints and handles commit
        return quote
    
    quote = await create_with_retry(
        db=db,
        create_fn=create_quote_with_number,
        generate_number_fn=lambda: generate_quote_number(db, current_user.tenant_id),
        entity_name="quote",
    )
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
    
    # Recalculate total using the same pricing logic as create.
    quote.total_amount = get_order_subtotal(order)
    await db.commit()
    await db.refresh(quote)
    return QuoteResponse.model_validate(quote)


@router.delete("/{quote_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_quote(
    quote_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Delete a quote draft and revert the repair order back to draft."""
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
            detail="Cannot delete an approved quote",
        )

    # Quote deletion reverts the order to draft to keep workflow explicit:
    # Create/Update quote -> Send quote -> Customer action.
    order.status = RepairOrderStatus.DRAFT
    await db.delete(quote)
    await db.commit()
    await db.refresh(order)

    await broadcast_repair_order_update(
        tenant_id=str(order.tenant_id),
        customer_id=str(order.customer_id),
        order_id=str(order.id),
        order_number=order.order_number,
        status=order.status.value,
        updated_at=order.updated_at.isoformat() if order.updated_at else None,
    )


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
        .options(
            selectinload(RepairOrder.customer),
            selectinload(RepairOrder.vehicle),
            selectinload(RepairOrder.parts_usage).selectinload(PartsUsage.inventory_item),
        )
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

    # Force customer-facing send to use current totals (services + parts),
    # even if the quote draft was created before later edits.
    latest_total = get_order_subtotal(order)
    if quote.total_amount != latest_total:
        quote.total_amount = latest_total
    
    customer = order.customer
    if not customer or not customer.email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Customer email not found",
        )
    
    # Generate magic link token
    quote.approval_token = secrets.token_urlsafe(48)
    
    # Parse services and parts for email
    services_html = ""
    selected_services: list[dict] = []
    if order.internal_notes:
        try:
            notes_data = json.loads(order.internal_notes)
            selected_services = notes_data.get("selected_services", [])
        except (json.JSONDecodeError, TypeError, ValueError):
            selected_services = []
    if selected_services:
        services_html = '<div style="margin: 15px 0;"><strong>Services / Labor:</strong><ul style="margin: 10px 0; padding-left: 20px;">'
        for svc in selected_services:
            svc_name = svc.get("name", "Service")
            svc_price = Decimal(str(svc.get("base_price", "0")))
            services_html += f'<li style="margin: 5px 0;">{svc_name} - ${svc_price:,.2f}</li>'
        services_html += '</ul></div>'

    parts_html = ""
    if order.parts_usage:
        parts_html = '<div style="margin: 15px 0;"><strong>Parts:</strong><ul style="margin: 10px 0; padding-left: 20px;">'
        for pu in order.parts_usage:
            part_name = pu.inventory_item.name if pu.inventory_item else "Part"
            qty = pu.quantity or 0
            line_total = Decimal(str(pu.total_price or 0))
            parts_html += f'<li style="margin: 5px 0;">{part_name} x{qty} - ${line_total:,.2f}</li>'
        parts_html += '</ul></div>'

    labor_total = get_order_labor_total(order)
    parts_total = get_order_parts_total(order)
    
    # Build vehicle info
    vehicle = order.vehicle
    vehicle_info = ""
    if vehicle:
        vehicle_info = f"{vehicle.year or ''} {vehicle.make} {vehicle.model}".strip()
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
            {parts_html}
            <p style="margin: 8px 0 0 0; color: #4b5563; font-size: 14px;"><strong>Labor / Services:</strong> ${labor_total:,.2f}</p>
            <p style="margin: 4px 0 0 0; color: #4b5563; font-size: 14px;"><strong>Parts:</strong> ${parts_total:,.2f}</p>
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
    
    # Mark as sent and reset declined status if resending
    quote.sent_to_customer = True
    quote.sent_at = datetime.utcnow()
    if quote.is_declined:
        quote.is_declined = False
        quote.decline_notes = None
        order.status = RepairOrderStatus.QUOTED  # Back to quoted from declined
    
    # Auto-approval: if customer has a threshold and quote is within it, approve immediately
    # Only auto-approve if order is still in a pre-approval state (DRAFT, QUOTED, DECLINED)
    threshold = getattr(customer, 'auto_approval_threshold', None)
    auto_approved = False
    pre_approval_statuses = [RepairOrderStatus.DRAFT, RepairOrderStatus.QUOTED, RepairOrderStatus.DECLINED]
    if threshold is not None and quote.total_amount <= threshold and order.status in pre_approval_statuses:
        quote.is_approved = True
        quote.is_declined = False
        order.status = RepairOrderStatus.APPROVED
        auto_approved = True
    
    await db.commit()
    await db.refresh(quote)
    
    if auto_approved:
        # Send auto-approved confirmation instead of approval request
        await send_email(
            db=db,
            tenant_id=str(current_user.tenant_id),
            to=customer.email,
            subject=f"Quote {quote.quote_number} Auto-Approved - Truck Pit Stop",
            body=f"""
            <html><body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
                <h1 style="color: #d97706;">Truck Pit Stop</h1>
                <h2 style="color: #16a34a;">Quote Auto-Approved</h2>
                <p>Hi {customer.first_name},</p>
                <p>Your repair quote <strong>{quote.quote_number}</strong> for <strong>${quote.total_amount:,.2f}</strong> 
                has been <strong>automatically approved</strong> per your pre-authorization threshold of ${threshold:,.2f}.</p>
                {f'<p><strong>Vehicle:</strong> {vehicle_info}</p>' if vehicle_info else ''}
                <p><strong>Description:</strong> {order.description or 'General Repair'}</p>
                {services_html}
                {parts_html}
                <p style="margin: 8px 0 0 0; color: #4b5563; font-size: 14px;"><strong>Labor / Services:</strong> ${labor_total:,.2f}</p>
                <p style="margin: 4px 0 0 0; color: #4b5563; font-size: 14px;"><strong>Parts:</strong> ${parts_total:,.2f}</p>
                <p style="color: #666; font-size: 14px;">Work will begin shortly. We will notify you when your vehicle is being serviced.</p>
            </body></html>
            """,
            template_name="quote_auto_approved",
        )
    else:
        await send_email(
            db=db,
            tenant_id=str(current_user.tenant_id),
            to=customer.email,
            subject=f"Quote {quote.quote_number} Ready for Approval - Truck Pit Stop",
            body=html_body,
            template_name="quote_approval",
        )
    
    # SMS notification for quote with approval link
    if customer.phone:
        vi = f"{vehicle.year or ''} {vehicle.make} {vehicle.model}".strip() if vehicle else "your vehicle"
        if auto_approved:
            sms_body = f"Your repair for {vi} (${quote.total_amount:,.2f}) has been auto-approved. Work will begin shortly. Order #{order.order_number} - Truck Pit Stop"
        else:
            sms_body = f"Repair estimate for {vi}: ${quote.total_amount:,.2f}. Tap to approve: {approval_url} - Truck Pit Stop"
        try:
            await send_sms(db, str(current_user.tenant_id), customer.phone, sms_body,
                template_name="quote_sent_sms")
        except Exception:
            pass
    
    # Broadcast WebSocket event to notify customer portal.
    # If auto-approved, emit quote_approved to avoid "review quote" UX.
    ws_event_type = WSEventType.QUOTE_APPROVED if auto_approved else WSEventType.QUOTE_CREATED
    await broadcast_quote_event(
        tenant_id=str(order.tenant_id),
        customer_id=str(order.customer_id),
        quote_id=str(quote.id),
        quote_number=quote.quote_number,
        event_type=ws_event_type,
        order_id=str(order.id),
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
    await db.refresh(order)
    
    # Broadcast WebSocket updates
    await broadcast_quote_event(
        tenant_id=str(order.tenant_id),
        customer_id=str(order.customer_id),
        quote_id=str(quote.id),
        quote_number=quote.quote_number,
        event_type=WSEventType.QUOTE_APPROVED,
        order_id=str(order.id),
    )
    await broadcast_repair_order_update(
        tenant_id=str(order.tenant_id),
        customer_id=str(order.customer_id),
        order_id=str(order.id),
        order_number=order.order_number,
        status=order.status.value,
        updated_at=order.updated_at.isoformat() if order.updated_at else None,
    )
    
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
            .options(selectinload(RepairOrder.customer), selectinload(RepairOrder.vehicle))
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
    order.status = RepairOrderStatus.DECLINED  # New status for declined quotes
    await db.commit()
    await db.refresh(quote)
    await db.refresh(order)
    
    # Broadcast WebSocket updates
    await broadcast_quote_event(
        tenant_id=str(order.tenant_id),
        customer_id=str(order.customer_id),
        quote_id=str(quote.id),
        quote_number=quote.quote_number,
        event_type=WSEventType.QUOTE_DECLINED,
        order_id=str(order.id),
    )
    await broadcast_repair_order_update(
        tenant_id=str(order.tenant_id),
        customer_id=str(order.customer_id),
        order_id=str(order.id),
        order_number=order.order_number,
        status=order.status.value,
        updated_at=order.updated_at.isoformat() if order.updated_at else None,
    )
    
    # Notify shop managers via SMS (same as token-based decline)
    customer = order.customer
    vehicle = order.vehicle
    vi = f"{vehicle.year or ''} {vehicle.make} {vehicle.model}".strip() if vehicle else "vehicle"
    customer_name = f"{customer.first_name} {customer.last_name}" if customer else "Customer"
    
    # Find managers to notify
    result = await db.execute(
        select(User).where(
            and_(
                User.tenant_id == order.tenant_id,
                User.role.in_([UserRole.GARAGE_OWNER, UserRole.GARAGE_ADMIN]),
                User.is_active == True,
            )
        )
    )
    managers = result.scalars().all()
    
    notes_snippet = ""
    if body.notes:
        notes_snippet = f' Notes: "{body.notes[:50]}{"..." if len(body.notes) > 50 else ""}"'
    
    for manager in managers:
        if manager.phone:
            try:
                await send_sms(
                    db, str(order.tenant_id), manager.phone,
                    f"Quote DECLINED: {customer_name} declined ${quote.total_amount:,.2f} for {vi}. Order #{order.order_number}.{notes_snippet} - Truck Pit Stop",
                    template_name="quote_declined_shop"
                )
            except Exception:
                pass
    
    return QuoteResponse.model_validate(quote)


# ============ Magic Link Endpoints (no auth required) ============

@router.get("/token/{token}", response_model=QuoteDetailResponse)
@limiter.limit("10/minute")  # Rate limit to prevent token brute force
async def get_quote_by_token(
    request: Request,
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
        .options(
            selectinload(RepairOrder.customer),
            selectinload(RepairOrder.vehicle),
            selectinload(RepairOrder.parts_usage).selectinload(PartsUsage.inventory_item),
        )
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

    parts = []
    for pu in order.parts_usage:
        parts.append(
            {
                "name": pu.inventory_item.name if pu.inventory_item else "Part",
                "quantity": pu.quantity,
                "unit_price": str(pu.unit_price),
                "total_price": str(pu.total_price),
            }
        )
    
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
        parts=parts,
        labor_total=get_order_labor_total(order),
        parts_total=get_order_parts_total(order),
    )


@router.post("/token/{token}/approve", response_model=QuoteResponse)
@limiter.limit("5/minute")  # Rate limit approve actions
async def approve_quote_by_token(
    request: Request,
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
    # Keep token valid so customer can view their approved quote status
    await db.commit()
    await db.refresh(quote)
    await db.refresh(order)
    
    # Broadcast WebSocket updates
    await broadcast_quote_event(
        tenant_id=str(order.tenant_id),
        customer_id=str(order.customer_id),
        quote_id=str(quote.id),
        quote_number=quote.quote_number,
        event_type=WSEventType.QUOTE_APPROVED,
        order_id=str(order.id),
    )
    await broadcast_repair_order_update(
        tenant_id=str(order.tenant_id),
        customer_id=str(order.customer_id),
        order_id=str(order.id),
        order_number=order.order_number,
        status=order.status.value,
        updated_at=order.updated_at.isoformat() if order.updated_at else None,
    )
    
    return QuoteResponse.model_validate(quote)


@router.post("/token/{token}/decline", response_model=QuoteResponse)
@limiter.limit("5/minute")  # Rate limit decline actions
async def decline_quote_by_token(
    request: Request,
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
            .options(selectinload(RepairOrder.customer), selectinload(RepairOrder.vehicle))
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
    order.status = RepairOrderStatus.DECLINED  # New status instead of DRAFT
    # Keep token valid so customer can change their mind
    await db.commit()
    await db.refresh(quote)
    await db.refresh(order)
    
    # Broadcast WebSocket updates
    await broadcast_quote_event(
        tenant_id=str(order.tenant_id),
        customer_id=str(order.customer_id),
        quote_id=str(quote.id),
        quote_number=quote.quote_number,
        event_type=WSEventType.QUOTE_DECLINED,
        order_id=str(order.id),
    )
    await broadcast_repair_order_update(
        tenant_id=str(order.tenant_id),
        customer_id=str(order.customer_id),
        order_id=str(order.id),
        order_number=order.order_number,
        status=order.status.value,
        updated_at=order.updated_at.isoformat() if order.updated_at else None,
    )
    
    # Notify shop managers via SMS
    customer = order.customer
    vehicle = order.vehicle
    vi = f"{vehicle.year or ''} {vehicle.make} {vehicle.model}".strip() if vehicle else "vehicle"
    customer_name = f"{customer.first_name} {customer.last_name}" if customer else "Customer"
    
    # Find managers to notify
    result = await db.execute(
        select(User).where(
            and_(
                User.tenant_id == order.tenant_id,
                User.role.in_([UserRole.GARAGE_OWNER, UserRole.GARAGE_ADMIN]),
                User.is_active == True,
            )
        )
    )
    managers = result.scalars().all()
    
    notes_snippet = ""
    if body.notes:
        notes_snippet = f' Notes: "{body.notes[:50]}{"..." if len(body.notes) > 50 else ""}"'
    
    for manager in managers:
        if manager.phone:
            try:
                await send_sms(
                    db, str(order.tenant_id), manager.phone,
                    f"Quote DECLINED: {customer_name} declined ${quote.total_amount:,.2f} for {vi}. Order #{order.order_number}.{notes_snippet} - Truck Pit Stop",
                    template_name="quote_declined_shop"
                )
            except Exception:
                pass
    
    return QuoteResponse.model_validate(quote)
