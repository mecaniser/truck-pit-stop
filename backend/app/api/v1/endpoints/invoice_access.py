from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional
from uuid import UUID

import stripe
from fastapi import APIRouter, Depends, HTTPException, Response, Request, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.dependencies import get_db
from app.core.logging import get_logger
from app.core.metrics import record_payment, record_payment_error
from app.core.rate_limit import limiter
from app.core.redis import (
    get_consumed_invoice_access_payload,
    get_invoice_access_payload,
    get_portal_enrollment_payload,
    consume_invoice_access_token,
    consume_portal_enrollment_token,
    is_invoice_access_token_consumed,
    is_portal_enrollment_token_consumed,
    get_token_version,
)
from app.core.security import create_access_token, create_refresh_token, get_password_hash
from app.core.websocket import broadcast_payment_received, broadcast_repair_order_update
from app.core.password_policy import validate_password
from app.db.models.customer import Customer
from app.db.models.invoice import Invoice, InvoiceStatus
from app.db.models.payment import Payment, PaymentMethod as PaymentMethodEnum, PaymentStatus
from app.db.models.repair_order import RepairOrder, RepairOrderStatus
from app.db.models.tenant import Tenant
from app.db.models.user import User, UserRole
from app.db.models.vehicle import Vehicle
from app.services.invoice_access_service import (
    PORTAL_ENROLLMENT_TOKEN_TTL_SECONDS,
    generate_portal_enrollment_token,
)
from app.services.payment_number_service import allocate_next_payment_number

router = APIRouter()
logger = get_logger(__name__)
stripe.api_key = settings.STRIPE_SECRET_KEY


class TokenRequest(BaseModel):
    token: str


class ResolveInvoiceLinkResponse(BaseModel):
    invoice_id: str
    invoice_number: str
    order_number: str
    customer_name: str
    vehicle_info: str
    amount_due: Decimal
    subtotal: Decimal
    shop_supplies_amount: Decimal
    service_fee_amount: Decimal
    tax_amount: Decimal
    discount_amount: Decimal
    total_amount: Decimal
    status: str
    due_date: Optional[datetime] = None
    paid_at: Optional[datetime] = None
    is_paid: bool = False
    has_portal_account: bool = False
    requires_password_setup: bool = True


class GuestPaymentIntentResponse(BaseModel):
    client_secret: str
    payment_intent_id: str
    amount: Decimal
    stripe_account_id: Optional[str] = None


class ConfirmGuestPaymentRequest(BaseModel):
    token: str
    payment_intent_id: str


class ConfirmGuestPaymentResponse(BaseModel):
    status: str
    message: str
    invoice_id: str
    paid_at: Optional[datetime] = None
    portal_enrollment_token: Optional[str] = None
    portal_enrollment_expires_in: Optional[int] = None


class CreatePortalRequest(BaseModel):
    token: str
    new_password: Optional[str] = None


class CreatePortalResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    redirect_to: str
    user_exists: bool


def _set_auth_cookies(response: Response, access_token: str, refresh_token: str):
    """Set auth cookies for a newly authenticated user."""
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=settings.COOKIE_SECURE_EFFECTIVE,
        samesite=settings.COOKIE_SAMESITE,
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        path="/",
    )
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=settings.COOKIE_SECURE_EFFECTIVE,
        samesite=settings.COOKIE_SAMESITE,
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
        path="/api/v1/auth",
    )


async def _get_active_invoice_payload_or_400(token: str) -> dict:
    payload = await get_invoice_access_payload(token)
    if payload:
        return payload

    if await is_invoice_access_token_consumed(token):
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="This invoice link has already been used. Please request a new invoice link.",
        )

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Invalid or expired invoice link.",
    )


async def _get_invoice_payload_for_confirm_or_400(token: str) -> dict:
    payload = await get_invoice_access_payload(token)
    if payload:
        return payload

    consumed_payload = await get_consumed_invoice_access_payload(token)
    if consumed_payload:
        return consumed_payload

    if await is_invoice_access_token_consumed(token):
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="This invoice link has already been used. Please request a new invoice link.",
        )

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Invalid or expired invoice link.",
    )


async def _get_portal_auth_payload_or_400(token: str) -> tuple[dict, str]:
    invoice_payload = await get_invoice_access_payload(token)
    if invoice_payload:
        return invoice_payload, "invoice_access"

    portal_payload = await get_portal_enrollment_payload(token)
    if portal_payload:
        return portal_payload, "portal_enrollment"

    if await is_invoice_access_token_consumed(token) or await is_portal_enrollment_token_consumed(token):
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="This invoice link has already been used. Please request a new invoice link.",
        )

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Invalid or expired invoice link.",
    )


async def _load_invoice_context(
    db: AsyncSession,
    invoice_id: str,
) -> tuple[Invoice, RepairOrder, Customer, Optional[Vehicle]]:
    result = await db.execute(
        select(Invoice)
        .options(
            selectinload(Invoice.repair_order).selectinload(RepairOrder.customer),
            selectinload(Invoice.repair_order).selectinload(RepairOrder.vehicle),
        )
        .where(Invoice.id == UUID(invoice_id))
    )
    invoice = result.scalar_one_or_none()
    if not invoice or not invoice.repair_order or not invoice.repair_order.customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invoice not found.",
        )
    return invoice, invoice.repair_order, invoice.repair_order.customer, invoice.repair_order.vehicle


def _validate_invoice_link_subject(payload: dict, invoice: Invoice, order: RepairOrder) -> None:
    """Validate token subject fields against current DB records."""
    if str(order.customer_id) != payload.get("customer_id"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid invoice link.")
    if str(invoice.tenant_id) != payload.get("tenant_id"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid invoice link.")


def _validate_existing_customer_user(email_user: User, customer_id: UUID):
    if email_user.role != UserRole.CUSTOMER:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This email belongs to another account type. Please contact the shop for assistance.",
        )
    if email_user.customer_id and email_user.customer_id != customer_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This email is already linked to another account. Please contact the shop for assistance.",
        )


def _validate_new_password_or_400(password: str) -> None:
    """Run password policy and normalize unexpected validator failures to 400."""
    try:
        validate_password(password)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception(
            "invoice_access_password_validation_unexpected_error",
            error_type=type(exc).__name__,
        )
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

    _validate_existing_customer_user(email_user, customer.id)
    if not email_user.customer_id:
        email_user.customer_id = customer.id
        email_user.tenant_id = customer.tenant_id
        email_user.is_active = True
        try:
            await db.commit()
            await db.refresh(email_user)
        except IntegrityError:
            await db.rollback()
            result = await db.execute(select(User).where(User.customer_id == customer.id))
            user = result.scalar_one_or_none()
            if user:
                return user
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Portal account setup is in progress. Please retry in a moment.",
            )

    return email_user


@router.post("/resolve", response_model=ResolveInvoiceLinkResponse)
@limiter.limit("5/minute")
async def resolve_invoice_link(
    request: Request,
    body: TokenRequest,
    db: AsyncSession = Depends(get_db),
):
    payload = await _get_active_invoice_payload_or_400(body.token)
    invoice, order, customer, vehicle = await _load_invoice_context(db, payload["invoice_id"])

    # Safety check against tampering/inconsistent payload
    _validate_invoice_link_subject(payload, invoice, order)

    user_result = await db.execute(select(User).where(User.customer_id == customer.id))
    existing_user = user_result.scalar_one_or_none()

    vehicle_info = f"{vehicle.year or ''} {vehicle.make} {vehicle.model}".strip() if vehicle else "Vehicle"
    return ResolveInvoiceLinkResponse(
        invoice_id=str(invoice.id),
        invoice_number=invoice.invoice_number,
        order_number=order.order_number,
        customer_name=f"{customer.first_name} {customer.last_name}",
        vehicle_info=vehicle_info,
        amount_due=invoice.total_amount,
        subtotal=invoice.subtotal,
        shop_supplies_amount=invoice.shop_supplies_amount,
        service_fee_amount=invoice.service_fee_amount,
        tax_amount=invoice.tax_amount,
        discount_amount=invoice.discount_amount,
        total_amount=invoice.total_amount,
        status=invoice.status.value,
        due_date=invoice.due_date,
        paid_at=invoice.paid_at,
        is_paid=invoice.status == InvoiceStatus.PAID,
        has_portal_account=existing_user is not None,
        requires_password_setup=existing_user is None,
    )


@router.post("/create-payment-intent", response_model=GuestPaymentIntentResponse)
@limiter.limit("5/minute")
async def create_guest_payment_intent(
    request: Request,
    body: TokenRequest,
    db: AsyncSession = Depends(get_db),
):
    payload = await _get_active_invoice_payload_or_400(body.token)
    invoice, order, customer, _ = await _load_invoice_context(db, payload["invoice_id"])

    _validate_invoice_link_subject(payload, invoice, order)

    if invoice.status == InvoiceStatus.PAID:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invoice already paid.",
        )

    if invoice.total_amount < Decimal("0.50"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invoice amount is below the minimum charge amount ($0.50).",
        )

    stripe_customer_id = None
    try:
        if not customer.stripe_customer_id:
            stripe_customer = stripe.Customer.create(
                email=customer.email,
                name=f"{customer.first_name} {customer.last_name}",
                metadata={"customer_id": str(customer.id)},
            )
            customer.stripe_customer_id = stripe_customer.id
            await db.commit()
            logger.info("stripe_customer_created", customer_id=str(customer.id), stripe_customer_id=stripe_customer.id)
        stripe_customer_id = customer.stripe_customer_id

        result = await db.execute(select(Tenant).where(Tenant.id == invoice.tenant_id))
        tenant = result.scalar_one_or_none()

        amount_cents = int(invoice.total_amount * 100)
        metadata = {
            "invoice_id": str(invoice.id),
            "invoice_number": invoice.invoice_number,
            "tenant_id": str(invoice.tenant_id),
            "order_number": order.order_number,
            "customer_id": str(customer.id),
            "customer_name": f"{customer.first_name} {customer.last_name}".strip(),
        }
        if customer.email:
            metadata["customer_email"] = customer.email

        intent_params = {
            "amount": amount_cents,
            "currency": "usd",
            "metadata": metadata,
            "automatic_payment_methods": {"enabled": True},
        }

        if tenant and tenant.stripe_account_id and tenant.stripe_onboarding_complete:
            intent_params["stripe_account"] = tenant.stripe_account_id
            platform_fee = int(amount_cents * (settings.PLATFORM_FEE_PERCENT / 100))
            if platform_fee > 0:
                intent_params["application_fee_amount"] = platform_fee
            # Product decision: no connected-account customer mapping for now.
            # In connected-account mode we intentionally omit `customer` and
            # rely on metadata for dashboard context.
        elif stripe_customer_id:
            intent_params["customer"] = stripe_customer_id

        payment_intent = stripe.PaymentIntent.create(**intent_params)

        logger.info(
            "guest_payment_intent_created",
            invoice_id=str(invoice.id),
            payment_intent_id=payment_intent.id,
            connected_account=tenant.stripe_account_id if tenant and tenant.stripe_account_id else None,
        )

        connected_account_id = None
        if tenant and tenant.stripe_account_id and tenant.stripe_onboarding_complete:
            connected_account_id = tenant.stripe_account_id

        return GuestPaymentIntentResponse(
            client_secret=payment_intent.client_secret,
            payment_intent_id=payment_intent.id,
            amount=invoice.total_amount,
            stripe_account_id=connected_account_id,
        )
    except stripe.error.StripeError as e:
        logger.error(
            "stripe_create_guest_payment_intent_failed",
            invoice_id=str(invoice.id),
            error=str(e),
            error_type=type(e).__name__,
        )
        record_payment_error(error_type=type(e).__name__, provider="stripe")
        raise


@router.post("/confirm-payment", response_model=ConfirmGuestPaymentResponse)
@limiter.limit("10/minute")
async def confirm_guest_payment(
    request: Request,
    body: ConfirmGuestPaymentRequest,
    db: AsyncSession = Depends(get_db),
):
    payload = await _get_invoice_payload_for_confirm_or_400(body.token)
    invoice, order, customer, _ = await _load_invoice_context(db, payload["invoice_id"])

    _validate_invoice_link_subject(payload, invoice, order)

    existing_payment_result = await db.execute(
        select(Payment).where(
            Payment.invoice_id == invoice.id,
            Payment.stripe_payment_intent_id == body.payment_intent_id,
        )
    )
    existing_payment = existing_payment_result.scalar_one_or_none()
    if existing_payment:
        # Keep behavior idempotent for retries: consume if still active, then
        # issue a fresh short-lived portal enrollment token.
        await consume_invoice_access_token(body.token)
        portal_enrollment_token = None
        portal_enrollment_expires_in = None
        try:
            portal_enrollment_token = await generate_portal_enrollment_token(
                invoice=invoice,
                order=order,
                customer=customer,
            )
            portal_enrollment_expires_in = PORTAL_ENROLLMENT_TOKEN_TTL_SECONDS
        except Exception as e:
            logger.error(
                "portal_enrollment_token_generation_failed_after_guest_payment_retry",
                invoice_id=str(invoice.id),
                error=str(e),
            )
        return ConfirmGuestPaymentResponse(
            status="success",
            message="Payment already confirmed",
            invoice_id=str(invoice.id),
            paid_at=invoice.paid_at,
            portal_enrollment_token=portal_enrollment_token,
            portal_enrollment_expires_in=portal_enrollment_expires_in,
        )

    if invoice.status == InvoiceStatus.PAID:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invoice already paid.",
        )

    tenant_result = await db.execute(select(Tenant).where(Tenant.id == invoice.tenant_id))
    tenant = tenant_result.scalar_one_or_none()

    try:
        retrieve_params = {}
        if tenant and tenant.stripe_account_id and tenant.stripe_onboarding_complete:
            retrieve_params["stripe_account"] = tenant.stripe_account_id
        payment_intent = stripe.PaymentIntent.retrieve(body.payment_intent_id, **retrieve_params)
    except stripe.error.InvalidRequestError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid payment intent.")
    except stripe.error.StripeError as e:
        logger.error("stripe_retrieve_guest_payment_intent_failed", error=str(e))
        record_payment_error(error_type=type(e).__name__, provider="stripe")
        raise

    if payment_intent.status != "succeeded":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Payment not successful. Status: {payment_intent.status}",
        )

    if payment_intent.metadata.get("invoice_id") != str(invoice.id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Payment intent mismatch.")

    invoice.status = InvoiceStatus.PAID
    invoice.paid_at = datetime.now(timezone.utc)
    order.status = RepairOrderStatus.PAID

    payment_number = await allocate_next_payment_number(db, invoice.tenant_id)
    payment = Payment(
        tenant_id=invoice.tenant_id,
        invoice_id=invoice.id,
        payment_number=payment_number,
        amount=invoice.total_amount,
        method=PaymentMethodEnum.STRIPE,
        status=PaymentStatus.COMPLETED,
        stripe_payment_intent_id=body.payment_intent_id,
    )
    db.add(payment)

    await db.commit()
    await db.refresh(invoice)
    await db.refresh(order)

    portal_enrollment_token = None
    portal_enrollment_expires_in = None
    consumed = await consume_invoice_access_token(body.token)
    if consumed is None:
        logger.info(
            "invoice_access_token_already_consumed_after_guest_payment",
            invoice_id=str(invoice.id),
        )

    try:
        portal_enrollment_token = await generate_portal_enrollment_token(
            invoice=invoice,
            order=order,
            customer=customer,
        )
        portal_enrollment_expires_in = PORTAL_ENROLLMENT_TOKEN_TTL_SECONDS
    except Exception as e:
        logger.error(
            "portal_enrollment_token_generation_failed_after_guest_payment",
            invoice_id=str(invoice.id),
            error=str(e),
        )

    await broadcast_payment_received(
        tenant_id=str(invoice.tenant_id),
        customer_id=str(order.customer_id),
        invoice_id=str(invoice.id),
        order_id=str(order.id),
    )
    await broadcast_repair_order_update(
        tenant_id=str(invoice.tenant_id),
        customer_id=str(order.customer_id),
        order_id=str(order.id),
        order_number=order.order_number,
        status=order.status.value,
        updated_at=order.updated_at.isoformat() if order.updated_at else None,
    )

    record_payment(status="success", payment_method="stripe", tenant_id=str(invoice.tenant_id))
    return ConfirmGuestPaymentResponse(
        status="success",
        message="Payment confirmed",
        invoice_id=str(invoice.id),
        paid_at=invoice.paid_at,
        portal_enrollment_token=portal_enrollment_token,
        portal_enrollment_expires_in=portal_enrollment_expires_in,
    )


@router.post("/create-portal", response_model=CreatePortalResponse)
@limiter.limit("5/minute")
async def create_portal_from_invoice_link(
    request: Request,
    response: Response,
    body: CreatePortalRequest,
    db: AsyncSession = Depends(get_db),
):
    payload, token_type = await _get_portal_auth_payload_or_400(body.token)
    invoice, order, customer, _ = await _load_invoice_context(db, payload["invoice_id"])

    _validate_invoice_link_subject(payload, invoice, order)

    result = await db.execute(select(User).where(User.customer_id == customer.id))
    user = result.scalar_one_or_none()
    user_exists = user is not None

    if not user:
        # If email is already in use, link safely when possible; otherwise fail with clear action.
        result = await db.execute(select(User).where(User.email == customer.email))
        email_user = result.scalar_one_or_none()
        if email_user:
            _validate_existing_customer_user(email_user, customer.id)
            user = email_user
            user.customer_id = customer.id
            user.tenant_id = customer.tenant_id
            user.is_active = True
            try:
                await db.commit()
                await db.refresh(user)
            except IntegrityError:
                await db.rollback()
                user = await _resolve_customer_user_after_conflict(db, customer)
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

    if token_type == "invoice_access":
        consumed = await consume_invoice_access_token(body.token)
    else:
        consumed = await consume_portal_enrollment_token(body.token)
    if consumed is None:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="This invoice link has already been used. Please request a new invoice link.",
        )

    token_version = await get_token_version(str(user.id))
    access_token = create_access_token(data={"sub": str(user.id)}, token_version=token_version)
    refresh_token = create_refresh_token(data={"sub": str(user.id)}, token_version=token_version)
    _set_auth_cookies(response, access_token, refresh_token)

    return CreatePortalResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        redirect_to=f"/portal/invoices/{invoice.id}",
        user_exists=user_exists,
    )
