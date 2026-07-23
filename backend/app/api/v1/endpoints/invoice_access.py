from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional
from uuid import UUID

import stripe
from fastapi import APIRouter, Depends, HTTPException, Response, Request, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.dependencies import get_db
from app.core.logging import get_logger
from app.core.vehicle_display import vehicle_display_label
from app.core.metrics import record_payment_error
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
from app.core.phone import normalize_phone
from app.core.websocket import broadcast_repair_order_update
from app.core.password_policy import validate_password
from app.db.models.customer import Customer
from app.db.models.invoice import Invoice, InvoiceStatus
from app.db.models.repair_order import RepairOrder
from app.db.models.tenant import Tenant
from app.db.models.user import User, UserRole
from app.db.models.user_customer_link import UserCustomerLink
from app.db.models.vehicle import Vehicle
from app.services.invoice_access_service import (
    PORTAL_ENROLLMENT_TOKEN_TTL_SECONDS,
    generate_portal_enrollment_token,
)
from app.services.pricing import get_order_checkout_breakdown
from app.services.pending_zelle_staff_notification_service import send_pending_zelle_submission_alert
from app.services.stripe_payment_finalization import finalize_stripe_invoice_payment
from app.services.stripe_customer_service import ensure_connected_stripe_customer
from app.services.stripe_platform_fee import platform_fee_amount_cents, platform_fee_percent_for

router = APIRouter()
logger = get_logger(__name__)
stripe.api_key = settings.STRIPE_SECRET_KEY

GUEST_INVOICE_PAYMENT_NOTE = "Payment made by guest invoice flow."


class TokenRequest(BaseModel):
    token: str


class ResolveInvoiceLinkResponse(BaseModel):
    invoice_id: str
    invoice_number: str
    order_number: str
    customer_name: str
    vehicle_info: str
    shop_name: Optional[str] = None
    shop_logo_url: Optional[str] = None
    amount_due: Decimal
    subtotal: Decimal
    shop_supplies_amount: Decimal
    service_fee_amount: Decimal
    tax_amount: Decimal
    discount_amount: Decimal
    total_amount: Decimal
    zelle_amount: Decimal  # total_amount minus service_fee (no processing fee for Zelle)
    status: str
    due_date: Optional[datetime] = None
    paid_at: Optional[datetime] = None
    is_paid: bool = False
    pending_zelle_confirmation: bool = False
    zelle_email: Optional[str] = None
    zelle_phone: Optional[str] = None
    zelle_qr_image: Optional[str] = None
    has_portal_account: bool = False
    requires_password_setup: bool = True
    stripe_payments_available: bool = False


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
    payment_note: Optional[str] = None


class CreatePortalRequest(BaseModel):
    token: str
    new_password: Optional[str] = None


class CreatePortalResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    redirect_to: str
    user_exists: bool


class SubmitGuestZellePaymentRequest(BaseModel):
    token: str
    sender_email: Optional[EmailStr] = None
    sender_phone: Optional[str] = None
    notes: Optional[str] = None


class SubmitGuestZellePaymentResponse(BaseModel):
    status: str
    message: str
    pending_zelle_confirmation: bool = True


def _cookie_domain() -> Optional[str]:
    domain = settings.COOKIE_DOMAIN.strip()
    return domain or None


def _set_auth_cookies(response: Response, access_token: str, refresh_token: str):
    """Set auth cookies for a newly authenticated user."""
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


def _validate_existing_customer_user(email_user: User):
    if email_user.role != UserRole.CUSTOMER:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This email belongs to another account type. Please contact the shop for assistance.",
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


@router.post("/resolve", response_model=ResolveInvoiceLinkResponse)
@limiter.limit("5/minute")
async def resolve_invoice_link(
    request: Request,
    body: TokenRequest,
    db: AsyncSession = Depends(get_db),
):
    payload = await _get_active_invoice_payload_or_400(body.token)
    invoice, order, customer, vehicle = await _load_invoice_context(db, payload["invoice_id"])
    tenant_result = await db.execute(select(Tenant).where(Tenant.id == invoice.tenant_id))
    tenant = tenant_result.scalar_one_or_none()

    # Safety check against tampering/inconsistent payload
    _validate_invoice_link_subject(payload, invoice, order)

    user_result = await db.execute(select(User).where(User.customer_id == customer.id))
    existing_user = user_result.scalar_one_or_none()
    if not existing_user:
        user_result = await db.execute(
            select(User).where(User.email == customer.email, User.role == UserRole.CUSTOMER)
        )
        existing_user = user_result.scalar_one_or_none()

    vehicle_info = vehicle_display_label(vehicle.year, vehicle.make, vehicle.model, vehicle.unit_number) if vehicle else "Vehicle"
    _zelle_amount = get_order_checkout_breakdown(order, tenant)["estimated_zelle_total"] if tenant else (
        Decimal(str(invoice.total_amount)) - Decimal(str(invoice.service_fee_amount or 0))
    ).quantize(Decimal("0.01"))
    return ResolveInvoiceLinkResponse(
        invoice_id=str(invoice.id),
        invoice_number=invoice.invoice_number,
        order_number=order.order_number,
        customer_name=f"{customer.first_name} {customer.last_name}",
        vehicle_info=vehicle_info,
        shop_name=tenant.name if tenant else None,
        shop_logo_url=tenant.logo_url if tenant else None,
        amount_due=invoice.total_amount,
        subtotal=invoice.subtotal,
        shop_supplies_amount=invoice.shop_supplies_amount,
        service_fee_amount=invoice.service_fee_amount,
        tax_amount=invoice.tax_amount,
        discount_amount=invoice.discount_amount,
        total_amount=invoice.total_amount,
        zelle_amount=_zelle_amount,
        status=invoice.status.value,
        due_date=invoice.due_date,
        paid_at=invoice.paid_at,
        is_paid=invoice.status == InvoiceStatus.PAID,
        pending_zelle_confirmation=invoice.pending_zelle_confirmation,
        zelle_email=tenant.zelle_email if tenant else None,
        zelle_phone=tenant.zelle_phone if tenant else None,
        zelle_qr_image=tenant.zelle_qr_image if tenant else None,
        has_portal_account=existing_user is not None,
        requires_password_setup=existing_user is None,
        stripe_payments_available=bool(
            tenant and tenant.stripe_account_id and tenant.stripe_onboarding_complete
        ),
    )


@router.post("/submit-zelle", response_model=SubmitGuestZellePaymentResponse)
@limiter.limit("5/minute")
async def submit_guest_zelle_payment(
    request: Request,
    body: SubmitGuestZellePaymentRequest,
    db: AsyncSession = Depends(get_db),
):
    payload = await _get_active_invoice_payload_or_400(body.token)
    invoice, order, customer, _ = await _load_invoice_context(db, payload["invoice_id"])

    _validate_invoice_link_subject(payload, invoice, order)

    if invoice.status == InvoiceStatus.PAID:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invoice already paid.")
    if invoice.status == InvoiceStatus.CANCELLED:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This invoice has been voided.")

    was_pending = invoice.pending_zelle_confirmation
    sender_email = str(body.sender_email).strip().lower() if body.sender_email else (customer.email.strip().lower() if customer and customer.email else None)
    sender_phone = normalize_phone(body.sender_phone or (customer.phone if customer else None))
    notes = body.notes.strip() if body.notes else None
    zelle_amount = invoice.total_amount - (invoice.service_fee_amount or 0)

    invoice.zelle_pending_submitted_at = datetime.now(timezone.utc)
    invoice.zelle_pending_sender_email = sender_email
    invoice.zelle_pending_sender_phone = sender_phone
    invoice.zelle_pending_last_reminder_at = None
    invoice.zelle_pending_reminder_count = 0
    if notes:
        existing_notes = (invoice.notes or "").strip()
        note_line = f"[Customer Zelle submit] {notes}"
        invoice.notes = f"{existing_notes}\n{note_line}".strip() if existing_notes else note_line

    await db.commit()
    await db.refresh(invoice)
    await db.refresh(invoice.repair_order)

    if not was_pending:
        customer_name = f"{customer.first_name} {customer.last_name}".strip() if customer else "Customer"
        try:
            await send_pending_zelle_submission_alert(
                db=db,
                tenant_id=invoice.tenant_id,
                order_id=invoice.repair_order.id,
                order_number=invoice.repair_order.order_number,
                invoice_number=invoice.invoice_number,
                customer_name=customer_name,
                amount=zelle_amount,
                source_label="guest invoice link",
                sender_email=sender_email,
                sender_phone=sender_phone,
            )
        except Exception as exc:
            logger.warning(
                "pending_zelle_submission_alert_failed",
                invoice_id=str(invoice.id),
                source="guest_invoice_access",
                error=str(exc),
            )

    await broadcast_repair_order_update(
        tenant_id=str(invoice.tenant_id),
        customer_id=str(invoice.repair_order.customer_id),
        order_id=str(invoice.repair_order_id),
        order_number=invoice.repair_order.order_number,
        status=invoice.repair_order.status.value,
        updated_at=invoice.repair_order.updated_at.isoformat() if invoice.repair_order.updated_at else None,
    )

    logger.info(
        "guest_zelle_submitted",
        invoice_id=str(invoice.id),
        order_id=str(order.id),
        customer_id=str(customer.id),
    )

    return SubmitGuestZellePaymentResponse(
        status="success",
        message="Zelle payment marked as submitted. Shop staff will confirm receipt.",
        pending_zelle_confirmation=invoice.pending_zelle_confirmation,
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
    if invoice.status == InvoiceStatus.CANCELLED:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This invoice has been voided.")

    if invoice.total_amount < Decimal("0.50"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invoice amount is below the minimum charge amount ($0.50).",
        )

    result = await db.execute(select(Tenant).where(Tenant.id == invoice.tenant_id))
    tenant = result.scalar_one_or_none()
    if not tenant or not tenant.stripe_account_id or not tenant.stripe_onboarding_complete:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This shop has not finished setting up Stripe payments.")

    try:
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

        stripe_customer_id = await ensure_connected_stripe_customer(
            db,
            customer,
            tenant.stripe_account_id,
        )

        intent_params = {
            "amount": amount_cents,
            "currency": "usd",
            "metadata": metadata,
            "customer": stripe_customer_id,
            "receipt_email": customer.email,
            "automatic_payment_methods": {"enabled": True},
        }

        fee_percent = platform_fee_percent_for(tenant)
        platform_fee = platform_fee_amount_cents(amount_cents, fee_percent)
        metadata["platform_fee_percent"] = str(fee_percent)
        metadata["platform_fee_amount_cents"] = str(platform_fee)
        metadata["stripe_connected_account_id"] = tenant.stripe_account_id
        intent_params["stripe_account"] = tenant.stripe_account_id
        if platform_fee > 0:
            intent_params["application_fee_amount"] = platform_fee

        payment_intent = stripe.PaymentIntent.create(**intent_params)

        logger.info(
            "guest_payment_intent_created",
            invoice_id=str(invoice.id),
            payment_intent_id=payment_intent.id,
            connected_account=tenant.stripe_account_id,
            platform_fee_percent=str(fee_percent),
            platform_fee_amount_cents=platform_fee,
        )

        return GuestPaymentIntentResponse(
            client_secret=payment_intent.client_secret,
            payment_intent_id=payment_intent.id,
            amount=invoice.total_amount,
            stripe_account_id=tenant.stripe_account_id,
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
    invoice, order, customer, vehicle = await _load_invoice_context(db, payload["invoice_id"])

    _validate_invoice_link_subject(payload, invoice, order)

    if invoice.status == InvoiceStatus.CANCELLED:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This invoice has been voided.")

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

    finalization = await finalize_stripe_invoice_payment(
        db=db,
        invoice=invoice,
        order=order,
        customer=customer,
        tenant=tenant,
        vehicle=vehicle,
        payment_intent=payment_intent,
        payment_note=GUEST_INVOICE_PAYMENT_NOTE,
    )

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

    return ConfirmGuestPaymentResponse(
        status="success",
        message="Payment confirmed" if finalization.created else "Payment already confirmed",
        invoice_id=str(invoice.id),
        paid_at=invoice.paid_at,
        portal_enrollment_token=portal_enrollment_token,
        portal_enrollment_expires_in=portal_enrollment_expires_in,
        payment_note=finalization.payment.notes or GUEST_INVOICE_PAYMENT_NOTE,
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

    # Cache all scalar values needed from ORM objects before any commit/rollback.
    # rollback() always expires ALL session objects regardless of expire_on_commit=False,
    # and accessing any attribute on an expired object raises MissingGreenlet in async mode.
    customer_tenant_id = customer.tenant_id
    invoice_id = invoice.id

    result = await db.execute(select(User).where(User.customer_id == customer.id))
    user = result.scalar_one_or_none()
    user_exists = user is not None

    if user:
        # Ensure UserCustomerLink exists — may be missing for users created before migration 043
        db.add(UserCustomerLink(user_id=user.id, customer_id=customer.id, tenant_id=customer_tenant_id))
        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()
            await db.refresh(user)  # rollback() always expires objects; re-hydrate so is_active is accessible

    if not user:
        # If email is already in use, link safely when possible; otherwise fail with clear action.
        result = await db.execute(select(User).where(User.email == customer.email))
        email_user = result.scalar_one_or_none()
        if email_user:
            _validate_existing_customer_user(email_user)
            user = email_user
            db.add(UserCustomerLink(
                user_id=user.id,
                customer_id=customer.id,
                tenant_id=customer_tenant_id,
            ))
            try:
                await db.commit()
                await db.refresh(user)
            except IntegrityError:
                await db.rollback()  # Link already exists — proceed
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
                tenant_id=customer_tenant_id,
                customer_id=customer.id,
                is_active=True,
                is_verified=False,
            )
            db.add(user)
            try:
                await db.flush()
                db.add(UserCustomerLink(
                    user_id=user.id,
                    customer_id=customer.id,
                    tenant_id=customer_tenant_id,
                ))
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
    # Returning users logging in via an invoice link should not burn the token —
    # the link must remain usable on future visits until it naturally expires (7 days).
    if not user_exists:
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
    access_token = create_access_token(data={"sub": str(user.id)}, token_version=token_version, tenant_id=str(customer_tenant_id))
    refresh_token = create_refresh_token(data={"sub": str(user.id)}, token_version=token_version, tenant_id=str(customer_tenant_id))
    _set_auth_cookies(response, access_token, refresh_token)

    return CreatePortalResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        redirect_to=f"/portal/invoices/{invoice_id}",
        user_exists=user_exists,
    )


@router.get("/pdf/{token}")
async def download_invoice_pdf_by_token(
    token: str,
    db: AsyncSession = Depends(get_db),
):
    """Public PDF download via invoice access token (no login required)."""
    from app.api.v1.endpoints.invoices import _load_line_items, _build_invoice_pdf_bytes

    payload = await get_invoice_access_payload(token)
    if not payload:
        if await is_invoice_access_token_consumed(token):
            raise HTTPException(status_code=status.HTTP_410_GONE, detail="This invoice link has already been used.")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired invoice link.")

    invoice, order, customer, vehicle = await _load_invoice_context(db, payload["invoice_id"])
    _validate_invoice_link_subject(payload, invoice, order)

    tenant_result = await db.execute(select(Tenant).where(Tenant.id == invoice.tenant_id))
    tenant = tenant_result.scalar_one_or_none()

    labor_items, parts_items = await _load_line_items(db, order.id, invoice)

    pdf_bytes = _build_invoice_pdf_bytes(
        invoice=invoice, order=order, customer=customer,
        vehicle=vehicle, tenant=tenant,
        labor_items=labor_items, parts_items=parts_items,
        invoice_access_url=None,
    )

    filename = f"Invoice-{invoice.invoice_number}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
