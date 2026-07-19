import json
import logging
import secrets
from html import escape
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Response, status, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload
from pydantic import BaseModel
from decimal import Decimal

from app.core.dependencies import get_db, get_current_active_user
from app.core.vehicle_display import vehicle_display_label
from app.core.config import settings
from app.core.rate_limit import limiter
from app.core.redis import (
    consume_quote_portal_enrollment_token,
    get_quote_portal_enrollment_payload,
    get_token_version,
    is_quote_portal_enrollment_token_consumed,
)
from app.core.metrics import record_quote
from app.core.security import create_access_token, create_refresh_token, get_password_hash
from app.core.password_policy import validate_password
from app.db.models.user import User, UserRole
from app.db.models.user_customer_link import UserCustomerLink
from app.db.models.repair_order import RepairOrder, RepairOrderStatus
from app.db.models.quote import Quote
from app.db.models.customer import Customer
from app.db.models.tenant import Tenant
from app.db.models.vehicle import Vehicle
from app.db.models.inventory import PartsUsage
from app.db.models.labor import Labor
from app.services.email_service import send_email
from app.services.provider_outbox_service import enqueue_email_notification
from app.services.tenant_branding import get_tenant_display_name
from app.services.twilio_service import send_sms
from app.services.pricing import (
    get_order_checkout_breakdown,
    get_order_labor_total,
    get_order_parts_total,
    get_order_total,
)
from app.services.price_build_service import (
    PriceBuildLockedError,
    PriceBuildService,
    PriceBuildValidationError,
)
from app.core.websocket import broadcast_quote_event, broadcast_repair_order_update, WSEventType
from app.services.quote_access_service import (
    QUOTE_PORTAL_ENROLLMENT_TOKEN_TTL_SECONDS,
    generate_quote_portal_enrollment_token,
)

router = APIRouter()
price_build_service = PriceBuildService()
logger = logging.getLogger(__name__)


def _money(value: object) -> Decimal:
    return Decimal(str(value or 0)).quantize(Decimal("0.01"))


def _format_money(value: object) -> str:
    return f"${_money(value):,.2f}"


def _build_quote_savings_html(order: RepairOrder) -> str:
    savings_rows: list[str] = []
    total_savings = Decimal("0.00")

    for pu in order.parts_usage or []:
        list_price = _money(pu.list_price if pu.list_price is not None else pu.unit_price)
        unit_price = _money(pu.unit_price)
        quantity = Decimal(str(pu.quantity or 0))
        part_savings = _money((list_price - unit_price) * quantity) if list_price > unit_price else Decimal("0.00")
        if part_savings <= 0:
            continue
        total_savings += part_savings
        part_name = pu.inventory_item.name if pu.inventory_item else "Part"
        savings_rows.append(
            f"""
            <tr>
                <td style="padding: 6px 0; color: #374151;">{escape(part_name)}</td>
                <td style="padding: 6px 0; color: #059669; font-weight: 700; text-align: right;">-{_format_money(part_savings)}</td>
            </tr>
            """
        )

    labor_discount = _money(order.labor_discount_amount)
    if labor_discount > 0:
        total_savings += labor_discount
        savings_rows.append(
            f"""
            <tr>
                <td style="padding: 6px 0; color: #374151;">Labor discount</td>
                <td style="padding: 6px 0; color: #059669; font-weight: 700; text-align: right;">-{_format_money(labor_discount)}</td>
            </tr>
            """
        )

    order_discount = _money(order.order_discount_amount)
    if order_discount > 0:
        total_savings += order_discount
        savings_rows.append(
            f"""
            <tr>
                <td style="padding: 6px 0; color: #374151;">Order discount</td>
                <td style="padding: 6px 0; color: #059669; font-weight: 700; text-align: right;">-{_format_money(order_discount)}</td>
            </tr>
            """
        )

    if total_savings <= 0:
        return ""

    rows_html = "".join(savings_rows)
    return f"""
    <div style="margin: 18px 0; padding: 14px 16px; background: #ecfdf5; border: 1px solid #a7f3d0; border-radius: 8px;">
        <p style="margin: 0 0 8px 0; color: #047857; font-size: 14px; font-weight: 700;">Customer savings</p>
        <table role="presentation" cellspacing="0" cellpadding="0" style="width: 100%; border-collapse: collapse; font-size: 14px;">
            {rows_html}
            <tr>
                <td style="padding: 8px 0 0 0; border-top: 1px solid #a7f3d0; color: #047857; font-weight: 800;">Total customer savings</td>
                <td style="padding: 8px 0 0 0; border-top: 1px solid #a7f3d0; color: #047857; font-weight: 800; text-align: right;">{_format_money(total_savings)}</td>
            </tr>
        </table>
    </div>
    """


def _build_quote_checkout_html(order: RepairOrder, tenant: Tenant) -> str:
    breakdown = get_order_checkout_breakdown(order, tenant)
    fee_rows: list[str] = []
    for label, key in (
        ("Repair total", "repair_total"),
        ("Shop supplies", "shop_supplies_amount"),
        ("Card processing fee", "service_fee_amount"),
        ("Estimated tax", "tax_amount"),
    ):
        amount = breakdown[key]
        if key != "repair_total" and amount <= 0:
            continue
        fee_rows.append(
            f"""
            <tr>
                <td style="padding: 5px 0; color: #4b5563;">{label}</td>
                <td style="padding: 5px 0; color: #111827; font-weight: 700; text-align: right;">{_format_money(amount)}</td>
            </tr>
            """
        )

    zelle_savings = breakdown["zelle_savings_amount"]
    zelle_note = (
        f'<p style="margin: 8px 0 0 0; color: #047857; font-size: 13px;"><strong>Zelle saves {_format_money(zelle_savings)}</strong> compared with card checkout.</p>'
        if zelle_savings > 0
        else ""
    )
    return f"""
    <div style="margin: 14px 0 0 0; padding: 12px; background: #fff7ed; border: 1px solid #fed7aa; border-radius: 8px;">
        <p style="margin: 0 0 8px 0; color: #9a3412; font-size: 13px; font-weight: 800; text-transform: uppercase; letter-spacing: .04em;">Estimated checkout total</p>
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border-collapse: collapse; font-size: 14px;">
            {''.join(fee_rows)}
            <tr>
                <td style="padding: 8px 0 0 0; border-top: 1px solid #fed7aa; color: #111827; font-weight: 800;">Pay by card</td>
                <td style="padding: 8px 0 0 0; border-top: 1px solid #fed7aa; color: #111827; font-weight: 800; text-align: right;">{_format_money(breakdown['estimated_card_total'])}</td>
            </tr>
            <tr>
                <td style="padding: 5px 0 0 0; color: #047857; font-weight: 800;">Pay by Zelle</td>
                <td style="padding: 5px 0 0 0; color: #047857; font-weight: 800; text-align: right;">{_format_money(breakdown['estimated_zelle_total'])}</td>
            </tr>
        </table>
        {zelle_note}
        <p style="margin: 8px 0 0 0; color: #6b7280; font-size: 12px;">Final payment total may vary if the invoice changes before checkout.</p>
    </div>
    """


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
    labor_discount_amount: Decimal = Decimal("0.00")
    order_discount_amount: Decimal = Decimal("0.00")
    shop_supplies_amount: Decimal = Decimal("0.00")
    service_fee_amount: Decimal = Decimal("0.00")
    tax_amount: Decimal = Decimal("0.00")
    estimated_card_total: Decimal = Decimal("0.00")
    estimated_zelle_total: Decimal = Decimal("0.00")
    zelle_savings_amount: Decimal = Decimal("0.00")
    shop_name: Optional[str] = None
    shop_logo_url: Optional[str] = None
    has_portal_account: bool = False
    requires_password_setup: bool = True


class QuotePortalResolveResponse(BaseModel):
    has_portal_account: bool
    requires_password_setup: bool
    portal_enrollment_token: str
    portal_enrollment_expires_in: int


class QuotePortalCreateRequest(BaseModel):
    token: str
    new_password: Optional[str] = None


class QuotePortalCreateResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    redirect_to: str
    user_exists: bool


def _cookie_domain() -> Optional[str]:
    domain = settings.COOKIE_DOMAIN.strip()
    return domain or None


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


def _set_auth_cookies(response: Response, access_token: str, refresh_token: str):
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=settings.COOKIE_SECURE_EFFECTIVE,
        samesite=settings.COOKIE_SAMESITE,
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        domain=_cookie_domain(),
        path="/",
    )
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=settings.COOKIE_SECURE_EFFECTIVE,
        samesite=settings.COOKIE_SAMESITE,
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
        domain=_cookie_domain(),
        path="/api/v1/auth",
    )


def _quote_token_reference_time(quote: Quote) -> datetime:
    ref = quote.sent_at or quote.created_at
    if ref.tzinfo is None:
        return ref.replace(tzinfo=timezone.utc)
    return ref


def _validate_quote_token_not_expired_or_400(quote: Quote) -> None:
    expires_at = _quote_token_reference_time(quote) + timedelta(days=7)
    if datetime.now(timezone.utc) > expires_at:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Quote link expired. Please contact the shop for a new quote link.",
        )


async def _load_quote_context_by_token_or_400(
    db: AsyncSession,
    token: str,
    *,
    include_parts: bool = False,
) -> tuple[Quote, RepairOrder]:
    result = await db.execute(select(Quote).where(Quote.approval_token == token))
    quote = result.scalar_one_or_none()
    if not quote:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Quote not found or link expired",
        )

    _validate_quote_token_not_expired_or_400(quote)

    order_query = (
        select(RepairOrder)
        .where(RepairOrder.id == quote.repair_order_id)
        .options(
            selectinload(RepairOrder.customer),
            selectinload(RepairOrder.vehicle),
        )
    )
    if include_parts:
        order_query = order_query.options(
            selectinload(RepairOrder.parts_usage).selectinload(PartsUsage.inventory_item),
        )
    result = await db.execute(order_query)
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Repair order not found",
        )
    return quote, order


async def _get_quote_portal_enrollment_payload_or_400(token: str) -> dict:
    payload = await get_quote_portal_enrollment_payload(token)
    if payload:
        return payload

    if await is_quote_portal_enrollment_token_consumed(token):
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="This portal link has already been used. Please return to your quote link.",
        )

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Invalid or expired portal link.",
    )


def _validate_quote_portal_subject(payload: dict, quote: Quote, order: RepairOrder) -> None:
    if str(quote.id) != payload.get("quote_id"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid portal link.")
    if str(order.customer_id) != payload.get("customer_id"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid portal link.")
    if str(order.tenant_id) != payload.get("tenant_id"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid portal link.")


def _validate_existing_customer_user(email_user: User) -> None:
    if email_user.role != UserRole.CUSTOMER:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This email belongs to another account type. Please contact the shop for assistance.",
        )


def _validate_new_password_or_400(password: str) -> None:
    try:
        validate_password(password)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid password. Please choose a stronger password and try again.",
        ) from exc


async def _resolve_customer_user_after_conflict(db: AsyncSession, customer: Customer) -> User:
    """Recover canonical customer user after unique-key races."""
    result = await db.execute(select(User).where(User.customer_id == customer.id))
    user = result.scalar_one_or_none()
    if user:
        return user

    result = await db.execute(select(User).where(User.email == customer.email))
    email_user = result.scalar_one_or_none()
    if not email_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Portal account setup is in progress. Please retry in a moment.",
        )

    _validate_existing_customer_user(email_user)
    db.add(UserCustomerLink(
        user_id=email_user.id,
        customer_id=customer.id,
        tenant_id=customer.tenant_id,
    ))
    try:
        await db.commit()
        await db.refresh(email_user)
    except IntegrityError:
        await db.rollback()  # Link already exists — that's fine

    return email_user


async def _ensure_user_customer_link(
    db: AsyncSession,
    *,
    user_id: UUID,
    customer_id: UUID,
    tenant_id: UUID,
) -> bool:
    result = await db.execute(
        select(UserCustomerLink).where(
            UserCustomerLink.user_id == user_id,
            UserCustomerLink.tenant_id == tenant_id,
        )
    )
    link = result.scalar_one_or_none()
    if link:
        if link.customer_id != customer_id:
            link.customer_id = customer_id
            return True
        return False

    db.add(UserCustomerLink(user_id=user_id, customer_id=customer_id, tenant_id=tenant_id))
    return True


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
    if order.is_internal:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Internal fleet repair orders are not quoted to a customer",
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
    
    # Quote total is the customer-facing net total after manager discounts.
    total_amount = get_order_total(order)
    
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
    record_quote(status="created", tenant_id=str(current_user.tenant_id))
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
    
    # Recalculate total using the same customer-facing pricing logic as create.
    quote.total_amount = get_order_total(order)
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
    current_user_id = current_user.id
    current_tenant_id = current_user.tenant_id
    
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
    
    if current_tenant_id != order.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )

    # An empty order has nothing to quote — refuse to send it (the UI disables the
    # button, but guard the API too so a direct call can't send a blank quote).
    labor_count = await db.execute(
        select(func.count(Labor.id)).where(Labor.repair_order_id == order.id)
    )
    if (labor_count.scalar() or 0) == 0 and len(order.parts_usage) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Add at least one operation, labor line, or part before sending this quote.",
        )

    tenant_result = await db.execute(select(Tenant).where(Tenant.id == order.tenant_id))
    tenant = tenant_result.scalar_one_or_none()
    shop_name = tenant.name if tenant and tenant.name else "Your repair shop"

    # Force customer-facing send to use current totals from the price builder,
    # even if the quote draft was created before later edits.
    try:
        pb_order = await price_build_service.load_order(db, order.id)
        if pb_order.pricing_locked_at is None:
            try:
                await price_build_service.recalculate_order(db, pb_order)
            except (PriceBuildValidationError, PriceBuildLockedError):
                # Keep flow non-blocking: quote can still be sent with current values.
                pass
        refreshed_result = await db.execute(
            select(RepairOrder)
            .where(RepairOrder.id == order.id)
            .options(
                selectinload(RepairOrder.customer),
                selectinload(RepairOrder.vehicle),
                selectinload(RepairOrder.parts_usage).selectinload(PartsUsage.inventory_item),
            )
        )
        refreshed_order = refreshed_result.scalar_one_or_none()
        if refreshed_order:
            order = refreshed_order
    except Exception as exc:
        # A database error during the optional price refresh leaves PostgreSQL
        # transactions aborted until rollback. Quote sending should continue
        # from the last persisted totals if the refresh cannot complete.
        logger.warning(
            "quote_price_refresh_failed",
            extra={"quote_id": str(quote_id), "repair_order_id": str(order.id), "error": str(exc)},
        )
        await db.rollback()
        refreshed_quote_result = await db.execute(select(Quote).where(Quote.id == quote_id))
        refreshed_quote = refreshed_quote_result.scalar_one_or_none()
        if not refreshed_quote:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Quote not found",
            )
        refreshed_order_result = await db.execute(
            select(RepairOrder)
            .where(RepairOrder.id == refreshed_quote.repair_order_id)
            .options(
                selectinload(RepairOrder.customer),
                selectinload(RepairOrder.vehicle),
                selectinload(RepairOrder.parts_usage).selectinload(PartsUsage.inventory_item),
            )
        )
        refreshed_order = refreshed_order_result.scalar_one_or_none()
        if not refreshed_order:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Repair order not found",
            )
        quote = refreshed_quote
        order = refreshed_order
        tenant_result = await db.execute(select(Tenant).where(Tenant.id == order.tenant_id))
        tenant = tenant_result.scalar_one_or_none()
        shop_name = tenant.name if tenant and tenant.name else "Your repair shop"
    latest_total = get_order_total(order)
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
    savings_html = _build_quote_savings_html(order)
    checkout_html = _build_quote_checkout_html(order, tenant) if tenant else ""
    
    # Build vehicle info
    vehicle = order.vehicle
    vehicle_info = ""
    if vehicle:
        vehicle_info = vehicle_display_label(vehicle.year, vehicle.make, vehicle.model, vehicle.unit_number)
        if vehicle.vin:
            vehicle_info += f" (VIN: {vehicle.vin[-6:]})"
    
    # Build magic link URL
    approval_url = f"{settings.FRONTEND_URL}/quote/{quote.approval_token}"
    
    html_body = f"""
    <html>
    <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
        <div style="text-align: center; margin-bottom: 30px;">
            <h1 style="color: #d97706; margin: 0;">🔧 {shop_name}</h1>
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
            {savings_html}
            {checkout_html}
            <hr style="border: none; border-top: 1px solid #e5e7eb; margin: 15px 0;">
            <p style="margin: 0; font-size: 28px; color: #d97706; text-align: center;"><strong>Repair total: ${quote.total_amount:,.2f}</strong></p>
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
    quote.sent_at = datetime.now(timezone.utc)
    quote.sent_by_user_id = current_user_id
    if order.pricing_locked_at is None:
        order.pricing_locked_at = quote.sent_at
    order.pricing_lock_reason = "quote_sent"
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
    
    if auto_approved:
        email_subject = f"Quote {quote.quote_number} Auto-Approved - {shop_name}"
        email_body = f"""
            <html><body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
                <h1 style="color: #d97706;">{shop_name}</h1>
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
            """
        email_template_name = "quote_auto_approved"
    else:
        email_subject = f"Quote {quote.quote_number} Ready for Approval - {shop_name}"
        email_body = html_body
        email_template_name = "quote_approval"

    outbox_event = None
    if settings.PROVIDER_OUTBOX_ENABLED:
        # The business state and durable delivery record commit together. The
        # worker reads the notification after commit, keeping Resend off the
        # request path and out of the request database transaction.
        outbox_event = await enqueue_email_notification(
            db,
            tenant_id=current_tenant_id,
            aggregate_type="quote",
            aggregate_id=quote.id,
            idempotency_key=f"quote-email:{quote.id}:{quote.approval_token}",
            recipient=customer.email,
            subject=email_subject,
            body=email_body,
            template_name=email_template_name,
            sender_name=shop_name,
        )

    await db.commit()
    await db.refresh(quote)
    if auto_approved:
        record_quote(status="approved", tenant_id=str(current_tenant_id))

    # Keep the old behavior until the dedicated Railway worker is live and the
    # feature flag is explicitly enabled. That makes this migration deployable
    # without ever queueing customer emails into an unserved system.
    if outbox_event is None:
        await send_email(
            db=db,
            tenant_id=str(current_tenant_id),
            to=customer.email,
            subject=email_subject,
            body=email_body,
            template_name=email_template_name,
            sender_name=shop_name,
        )
    
    # SMS notification for quote with approval link
    if customer.phone:
        vi = vehicle_display_label(vehicle.year, vehicle.make, vehicle.model, vehicle.unit_number) if vehicle else "your vehicle"
        if auto_approved:
            sms_body = f"Your repair for {vi} (${quote.total_amount:,.2f}) has been auto-approved. Work will begin shortly. Order #{order.order_number} - {shop_name}"
        else:
            sms_body = f"Repair estimate for {vi}: ${quote.total_amount:,.2f}. Tap to approve: {approval_url} - {shop_name}"
        try:
            await send_sms(
                db,
                str(current_tenant_id),
                customer.phone,
                sms_body,
                template_name="quote_sent_sms",
                customer_id=customer.id,
                source="automated",
            )
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
    record_quote(status="approved", tenant_id=str(order.tenant_id))
    
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
    await db.refresh(order, attribute_names=["customer", "vehicle"])
    record_quote(status="declined", tenant_id=str(order.tenant_id))
    
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
    vi = vehicle_display_label(vehicle.year, vehicle.make, vehicle.model, vehicle.unit_number) if vehicle else "vehicle"
    customer_name = f"{customer.first_name} {customer.last_name}" if customer else "Customer"
    shop_name = await get_tenant_display_name(db, order.tenant_id)
    
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
                    f"Quote DECLINED: {customer_name} declined ${quote.total_amount:,.2f} for {vi}. Order #{order.order_number}.{notes_snippet} - {shop_name}",
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
    quote, order = await _load_quote_context_by_token_or_400(db, token, include_parts=True)
    
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
    user_result = await db.execute(select(User).where(User.customer_id == order.customer_id))
    existing_user = user_result.scalar_one_or_none()
    if not existing_user and customer:
        user_result = await db.execute(
            select(User).where(User.email == customer.email, User.role == UserRole.CUSTOMER)
        )
        existing_user = user_result.scalar_one_or_none()
    tenant_result = await db.execute(select(Tenant).where(Tenant.id == order.tenant_id))
    tenant = tenant_result.scalar_one_or_none()
    checkout = get_order_checkout_breakdown(order, tenant) if tenant else {
        "shop_supplies_amount": Decimal("0.00"),
        "service_fee_amount": Decimal("0.00"),
        "tax_amount": Decimal("0.00"),
        "estimated_card_total": quote.total_amount,
        "estimated_zelle_total": quote.total_amount,
        "zelle_savings_amount": Decimal("0.00"),
    }

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
        labor_discount_amount=Decimal(str(order.labor_discount_amount or 0)),
        order_discount_amount=Decimal(str(order.order_discount_amount or 0)),
        shop_supplies_amount=checkout["shop_supplies_amount"],
        service_fee_amount=checkout["service_fee_amount"],
        tax_amount=checkout["tax_amount"],
        estimated_card_total=checkout["estimated_card_total"],
        estimated_zelle_total=checkout["estimated_zelle_total"],
        zelle_savings_amount=checkout["zelle_savings_amount"],
        shop_name=tenant.name if tenant else None,
        shop_logo_url=tenant.logo_url if tenant else None,
        has_portal_account=existing_user is not None,
        requires_password_setup=existing_user is None,
    )


@router.post("/token/{token}/approve", response_model=QuoteResponse)
@limiter.limit("5/minute")  # Rate limit approve actions
async def approve_quote_by_token(
    request: Request,
    token: str,
    db: AsyncSession = Depends(get_db),
):
    """Approve quote via magic link - no auth required"""
    quote, order = await _load_quote_context_by_token_or_400(db, token)
    
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
    record_quote(status="approved", tenant_id=str(order.tenant_id))
    
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


@router.post("/token/{token}/portal-resolve", response_model=QuotePortalResolveResponse)
@limiter.limit("5/minute")
async def resolve_quote_portal_access(
    request: Request,
    token: str,
    db: AsyncSession = Depends(get_db),
):
    quote, order = await _load_quote_context_by_token_or_400(db, token)
    if not quote.is_approved:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Portal onboarding is available after quote approval.",
        )
    if not order.customer:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")

    result = await db.execute(select(User).where(User.customer_id == order.customer_id))
    existing_user = result.scalar_one_or_none()
    if not existing_user:
        result = await db.execute(
            select(User).where(User.email == order.customer.email, User.role == UserRole.CUSTOMER)
        )
        existing_user = result.scalar_one_or_none()

    portal_enrollment_token = await generate_quote_portal_enrollment_token(
        quote=quote,
        order=order,
        customer=order.customer,
    )

    return QuotePortalResolveResponse(
        has_portal_account=existing_user is not None,
        requires_password_setup=existing_user is None,
        portal_enrollment_token=portal_enrollment_token,
        portal_enrollment_expires_in=QUOTE_PORTAL_ENROLLMENT_TOKEN_TTL_SECONDS,
    )


@router.post("/portal/create", response_model=QuotePortalCreateResponse)
@limiter.limit("5/minute")
async def create_portal_from_quote_link(
    request: Request,
    response: Response,
    body: QuotePortalCreateRequest,
    db: AsyncSession = Depends(get_db),
):
    payload = await _get_quote_portal_enrollment_payload_or_400(body.token)
    try:
        quote_id = UUID(payload["quote_id"])
    except (KeyError, ValueError, TypeError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired portal link.")

    result = await db.execute(select(Quote).where(Quote.id == quote_id))
    quote = result.scalar_one_or_none()
    if not quote:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quote not found.")

    result = await db.execute(
        select(RepairOrder)
        .where(RepairOrder.id == quote.repair_order_id)
        .options(selectinload(RepairOrder.customer))
    )
    order = result.scalar_one_or_none()
    if not order or not order.customer:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found.")

    if not quote.is_approved:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Portal onboarding is available after quote approval.",
        )

    _validate_quote_portal_subject(payload, quote, order)
    customer = order.customer

    result = await db.execute(select(User).where(User.customer_id == customer.id))
    user = result.scalar_one_or_none()
    user_exists = user is not None

    if user:
        # Ensure UserCustomerLink exists — may be missing for users created before migration 043
        if user.customer_id != customer.id:
            user.customer_id = customer.id
        if await _ensure_user_customer_link(
            db,
            user_id=user.id,
            customer_id=customer.id,
            tenant_id=customer.tenant_id,
        ):
            await db.commit()
            await db.refresh(user)

    if not user:
        result = await db.execute(select(User).where(User.email == customer.email))
        email_user = result.scalar_one_or_none()
        if email_user:
            _validate_existing_customer_user(email_user)
            user = email_user
            if user.customer_id != customer.id:
                user.customer_id = customer.id
            link_added = await _ensure_user_customer_link(
                db,
                user_id=user.id,
                customer_id=customer.id,
                tenant_id=customer.tenant_id,
            )
            if link_added:
                await db.commit()
                await db.refresh(user)
            user_exists = True
        else:
            if not body.new_password:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Password is required to create your portal account.",
                )
            _validate_new_password_or_400(body.new_password)
            user = User(
                email=customer.email,
                hashed_password=get_password_hash(body.new_password),
                first_name=customer.first_name,
                last_name=customer.last_name,
                phone=customer.phone,
                role=UserRole.CUSTOMER,
                tenant_id=customer.tenant_id,
                customer_id=customer.id,
                is_active=True,
                is_verified=False,
            )
            db.add(user)
            try:
                await db.flush()
                db.add(UserCustomerLink(user_id=user.id, customer_id=customer.id, tenant_id=customer.tenant_id))
                await db.commit()
                await db.refresh(user)
                user_exists = False
            except IntegrityError:
                await db.rollback()
                user = await _resolve_customer_user_after_conflict(db, customer)
                user_exists = True

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account is inactive. Please contact the shop.",
        )

    # Only consume the token when creating a new account (first-time enrollment).
    # Returning users logging in via a quote link should not burn the token —
    # the link must remain usable on future visits until it naturally expires.
    if not user_exists:
        consumed = await consume_quote_portal_enrollment_token(body.token)
        if consumed is None:
            raise HTTPException(
                status_code=status.HTTP_410_GONE,
                detail="This portal link has already been used. Please return to your quote link.",
            )

    token_version = await get_token_version(str(user.id))
    access_token = create_access_token(data={"sub": str(user.id)}, token_version=token_version, tenant_id=str(customer.tenant_id))
    refresh_token = create_refresh_token(data={"sub": str(user.id)}, token_version=token_version, tenant_id=str(customer.tenant_id))
    _set_auth_cookies(response, access_token, refresh_token)

    return QuotePortalCreateResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        redirect_to="/portal",
        user_exists=user_exists,
    )


@router.post("/token/{token}/decline", response_model=QuoteResponse)
@limiter.limit("5/minute")  # Rate limit decline actions
async def decline_quote_by_token(
    request: Request,
    token: str,
    body: DeclineQuoteRequest,
    db: AsyncSession = Depends(get_db),
):
    """Decline quote via magic link - no auth required"""
    quote, order = await _load_quote_context_by_token_or_400(db, token)
    
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
    await db.refresh(order, attribute_names=["customer", "vehicle"])
    record_quote(status="declined", tenant_id=str(order.tenant_id))
    
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
    vi = vehicle_display_label(vehicle.year, vehicle.make, vehicle.model, vehicle.unit_number) if vehicle else "vehicle"
    customer_name = f"{customer.first_name} {customer.last_name}" if customer else "Customer"
    shop_name = await get_tenant_display_name(db, order.tenant_id)
    
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
                    f"Quote DECLINED: {customer_name} declined ${quote.total_amount:,.2f} for {vi}. Order #{order.order_number}.{notes_snippet} - {shop_name}",
                    template_name="quote_declined_shop"
                )
            except Exception:
                pass
    
    return QuoteResponse.model_validate(quote)
