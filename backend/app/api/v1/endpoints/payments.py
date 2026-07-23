from typing import List, Optional
from uuid import UUID
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from sqlalchemy.orm import selectinload
from pydantic import BaseModel, EmailStr
from decimal import Decimal
import stripe
from app.core.config import settings
from app.core.dependencies import get_db, get_current_active_user
from app.core.logging import get_logger
from app.core.metrics import record_payment, record_payment_error
from app.core.pagination import paginated_or_list
from app.core.rate_limit import limiter
from app.core.phone import normalize_phone
from app.db.models.user import User, UserRole
from app.db.models.customer import Customer
from app.db.models.invoice import Invoice, InvoiceStatus
from app.db.models.repair_order import RepairOrder, RepairOrderStatus
from app.db.models.payment import Payment, PaymentMethod as PaymentMethodEnum, PaymentStatus
from app.db.models.tenant import Tenant
from app.db.models.vehicle import Vehicle
from app.core.websocket import broadcast_payment_received, broadcast_repair_order_update
from app.services.invoice_notification_service import send_invoice_payment_confirmation_email
from app.services.pending_zelle_staff_notification_service import send_pending_zelle_submission_alert
from app.services.payment_number_service import allocate_next_payment_number
from app.services.stripe_payment_finalization import finalize_stripe_invoice_payment
from app.services.stripe_customer_service import ensure_connected_stripe_customer
from app.services.stripe_platform_fee import platform_fee_amount_cents, platform_fee_percent_for

logger = get_logger(__name__)

stripe.api_key = settings.STRIPE_SECRET_KEY

router = APIRouter()

PORTAL_PAYMENT_NOTE = "Payment made by customer portal flow."


class SetupIntentResponse(BaseModel):
    client_secret: str


class PaymentMethodResponse(BaseModel):
    id: str
    brand: str
    last4: str
    exp_month: int
    exp_year: int
    is_default: bool


class ConfigResponse(BaseModel):
    publishable_key: str


class PaymentIntentRequest(BaseModel):
    invoice_id: UUID


class PaymentIntentResponse(BaseModel):
    client_secret: str
    payment_intent_id: str
    amount: Decimal
    stripe_account_id: Optional[str] = None  # Connected account ID for Stripe Connect


class ConfirmPaymentRequest(BaseModel):
    invoice_id: UUID
    payment_intent_id: str


class ManualPaymentRequest(BaseModel):
    invoice_id: UUID
    method: str  # 'cash', 'zelle', 'check', 'ach', 'fleet_payment', 'other'
    notes: Optional[str] = None
    payment_provider: Optional[str] = None
    reference_number: Optional[str] = None
    authorization_number: Optional[str] = None
    zelle_sender_email: Optional[EmailStr] = None
    zelle_sender_phone: Optional[str] = None
    update_customer_from_sender: bool = False


class ZelleInfoResponse(BaseModel):
    zelle_email: Optional[str] = None
    zelle_phone: Optional[str] = None
    zelle_qr_image: Optional[str] = None
    garage_name: str
    stripe_payments_available: bool = False


class ManualPaymentResponse(BaseModel):
    status: str
    message: str
    warning: Optional[str] = None


class RevertPendingZelleRequest(BaseModel):
    invoice_id: UUID
    reason: Optional[str] = None


class SubmitCustomerZellePaymentRequest(BaseModel):
    invoice_id: UUID
    sender_email: Optional[EmailStr] = None
    sender_phone: Optional[str] = None
    notes: Optional[str] = None


class SubmitCustomerZellePaymentResponse(BaseModel):
    status: str
    message: str
    pending_zelle_confirmation: bool = True


def _normalize_phone(phone: Optional[str]) -> Optional[str]:
    return normalize_phone(phone)


def _normalize_email(email: Optional[str]) -> Optional[str]:
    if not email:
        return None
    normalized = email.strip().lower()
    return normalized or None


def _normalized_manual_payment_details(body: ManualPaymentRequest) -> tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
    """Normalize and validate staff-supplied settlement evidence."""
    provider = body.payment_provider.strip() if body.payment_provider else None
    reference = body.reference_number.strip() if body.reference_number else None
    authorization = body.authorization_number.strip() if body.authorization_number else None
    notes = body.notes.strip() if body.notes else None

    for label, value, maximum in (
        ("Payment provider", provider, 100),
        ("Reference number", reference, 255),
        ("Authorization number", authorization, 255),
        ("Payment notes", notes, 1000),
    ):
        if value and len(value) > maximum:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"{label} cannot exceed {maximum} characters",
            )

    if body.method == "ach" and not reference:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="A bank trace or transfer reference is required to confirm an ACH payment",
        )
    if body.method == "check" and not reference:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="A check number is required to confirm a check payment",
        )
    if body.method == "fleet_payment":
        if not provider:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="A fleet payment provider is required",
            )
        if not reference:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="A fleet check or payment code is required",
            )
        if not authorization:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="An authorization or approval number is required",
            )

    return provider, reference, authorization, notes


def _is_placeholder_walkin_customer(customer: Customer) -> bool:
    email = (customer.email or "").lower()
    first_name = (customer.first_name or "").lower()
    return (
        "@placeholder.dieselbridge.network" in email
        or first_name == "walk-in"
        or (customer.source or "").lower() == "walk_in"
    )


@router.get("/config", response_model=ConfigResponse)
async def get_stripe_config():
    """Get Stripe publishable key for frontend"""
    return ConfigResponse(publishable_key=settings.STRIPE_PUBLISHABLE_KEY)


@router.post("/setup-intent", response_model=SetupIntentResponse)
async def create_setup_intent(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Create a SetupIntent for saving a payment method"""
    if current_user.role != UserRole.CUSTOMER or not current_user.customer_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only customers can add payment methods",
        )
    
    # Get customer record
    result = await db.execute(select(Customer).where(Customer.id == current_user.customer_id))
    customer = result.scalar_one_or_none()
    
    if not customer:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")
    
    # Create or retrieve Stripe customer
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
        
        # Create SetupIntent
        setup_intent = stripe.SetupIntent.create(
            customer=customer.stripe_customer_id,
            payment_method_types=["card"],
        )
        
        return SetupIntentResponse(client_secret=setup_intent.client_secret)
    except stripe.error.StripeError as e:
        logger.error("stripe_setup_intent_failed", customer_id=str(customer.id), error=str(e))
        record_payment_error(error_type=type(e).__name__, provider="stripe")
        raise  # Re-raise to be handled by global exception handler


@router.get("/methods", response_model=List[PaymentMethodResponse])
async def list_payment_methods(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
    paginated: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """List customer's saved payment methods"""
    if current_user.role != UserRole.CUSTOMER or not current_user.customer_id:
        return paginated_or_list([], 0, skip, limit, paginated)
    
    # Get customer record
    result = await db.execute(select(Customer).where(Customer.id == current_user.customer_id))
    customer = result.scalar_one_or_none()
    
    if not customer or not customer.stripe_customer_id:
        return paginated_or_list([], 0, skip, limit, paginated)
    
    try:
        # Get payment methods from Stripe
        payment_methods = stripe.PaymentMethod.list(
            customer=customer.stripe_customer_id,
            type="card",
        )
        
        # Get default payment method
        stripe_customer = stripe.Customer.retrieve(customer.stripe_customer_id)
        default_pm_id = stripe_customer.invoice_settings.default_payment_method
        
        items = [
            PaymentMethodResponse(
                id=pm.id,
                brand=pm.card.brand,
                last4=pm.card.last4,
                exp_month=pm.card.exp_month,
                exp_year=pm.card.exp_year,
                is_default=pm.id == default_pm_id,
            )
            for pm in payment_methods.data
        ]
        total = len(items)
        response_items = items[skip : skip + limit] if paginated else items
        return paginated_or_list(response_items, total, skip, limit, paginated)
    except stripe.error.StripeError as e:
        logger.error("stripe_list_payment_methods_failed", customer_id=str(customer.id), error=str(e))
        record_payment_error(error_type=type(e).__name__, provider="stripe")
        raise


@router.delete("/methods/{payment_method_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_payment_method(
    payment_method_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Delete a saved payment method"""
    if current_user.role != UserRole.CUSTOMER or not current_user.customer_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    
    # Verify payment method belongs to this customer
    result = await db.execute(select(Customer).where(Customer.id == current_user.customer_id))
    customer = result.scalar_one_or_none()
    
    if not customer or not customer.stripe_customer_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No payment methods")
    
    # Verify ownership via Stripe
    try:
        pm = stripe.PaymentMethod.retrieve(payment_method_id)
        if pm.customer != customer.stripe_customer_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your payment method")
        
        stripe.PaymentMethod.detach(payment_method_id)
        logger.info("payment_method_deleted", customer_id=str(customer.id), payment_method_id=payment_method_id)
    except stripe.error.InvalidRequestError as e:
        logger.warning("stripe_delete_payment_method_failed", payment_method_id=payment_method_id, error=str(e))
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payment method not found")
    except stripe.error.StripeError as e:
        logger.error("stripe_delete_payment_method_error", payment_method_id=payment_method_id, error=str(e))
        record_payment_error(error_type=type(e).__name__, provider="stripe")
        raise


@router.post("/methods/{payment_method_id}/default", status_code=status.HTTP_204_NO_CONTENT)
async def set_default_payment_method(
    payment_method_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Set a payment method as default"""
    if current_user.role != UserRole.CUSTOMER or not current_user.customer_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    
    result = await db.execute(select(Customer).where(Customer.id == current_user.customer_id))
    customer = result.scalar_one_or_none()
    
    if not customer or not customer.stripe_customer_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No payment methods")
    
    # Verify ownership and set as default
    try:
        pm = stripe.PaymentMethod.retrieve(payment_method_id)
        if pm.customer != customer.stripe_customer_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your payment method")
        
        stripe.Customer.modify(
            customer.stripe_customer_id,
            invoice_settings={"default_payment_method": payment_method_id},
        )
        logger.info("default_payment_method_set", customer_id=str(customer.id), payment_method_id=payment_method_id)
    except stripe.error.InvalidRequestError as e:
        logger.warning("stripe_set_default_failed", payment_method_id=payment_method_id, error=str(e))
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payment method not found")
    except stripe.error.StripeError as e:
        logger.error("stripe_set_default_error", payment_method_id=payment_method_id, error=str(e))
        record_payment_error(error_type=type(e).__name__, provider="stripe")
        raise


@router.post("/create-payment-intent", response_model=PaymentIntentResponse)
async def create_payment_intent_for_invoice(
    body: PaymentIntentRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Create a PaymentIntent for an invoice"""
    if current_user.role != UserRole.CUSTOMER or not current_user.customer_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only customers can pay invoices")
    
    # Get invoice with repair order
    result = await db.execute(
        select(Invoice)
        .options(
            selectinload(Invoice.repair_order).selectinload(RepairOrder.customer),
            selectinload(Invoice.repair_order).selectinload(RepairOrder.vehicle),
        )
        .where(Invoice.id == body.invoice_id)
    )
    invoice = result.scalar_one_or_none()
    
    if not invoice:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found")
    
    # Verify customer owns this invoice
    if invoice.repair_order.customer_id != current_user.customer_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    customer = invoice.repair_order.customer
    if not customer:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")
    
    if invoice.status == InvoiceStatus.PAID:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invoice already paid")
    if invoice.status == InvoiceStatus.CANCELLED:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Voided invoices cannot be paid")
    
    # Stripe minimum is $0.50 USD
    if invoice.total_amount < Decimal("0.50"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invoice amount is below the minimum charge amount ($0.50)",
        )
    
    result = await db.execute(select(Customer).where(Customer.id == current_user.customer_id))
    customer = result.scalar_one_or_none()
    if not customer:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")

    result = await db.execute(select(Tenant).where(Tenant.id == invoice.tenant_id))
    tenant = result.scalar_one_or_none()
    if not tenant or not tenant.stripe_account_id or not tenant.stripe_onboarding_complete:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This shop has not finished setting up Stripe payments.")

    try:
        # Create PaymentIntent
        amount_cents = int(invoice.total_amount * 100)
        metadata = {
            "invoice_id": str(invoice.id),
            "invoice_number": invoice.invoice_number,
            "tenant_id": str(invoice.tenant_id),
            "order_number": invoice.repair_order.order_number if invoice.repair_order else "",
        }
        if customer:
            metadata["customer_id"] = str(customer.id)
            metadata["customer_name"] = f"{customer.first_name} {customer.last_name}".strip()
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
            "payment_intent_created",
            invoice_id=str(invoice.id),
            payment_intent_id=payment_intent.id,
            amount=float(invoice.total_amount),
            connected_account=tenant.stripe_account_id,
            platform_fee_percent=str(fee_percent),
            platform_fee_amount_cents=platform_fee,
        )
        
        # Return connected account ID if using Stripe Connect
        return PaymentIntentResponse(
            client_secret=payment_intent.client_secret,
            payment_intent_id=payment_intent.id,
            amount=invoice.total_amount,
            stripe_account_id=tenant.stripe_account_id,
        )
    except stripe.error.StripeError as e:
        logger.error(
            "stripe_create_payment_intent_failed",
            invoice_id=str(invoice.id),
            amount=float(invoice.total_amount),
            error=str(e),
            error_type=type(e).__name__,
        )
        record_payment_error(error_type=type(e).__name__, provider="stripe")
        raise


@router.post("/confirm-payment")
async def confirm_payment(
    body: ConfirmPaymentRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Confirm payment was successful and update invoice/repair order status"""
    if current_user.role != UserRole.CUSTOMER or not current_user.customer_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    
    # Get invoice (with repair order + vehicle eagerly loaded)
    result = await db.execute(
        select(Invoice)
        .options(selectinload(Invoice.repair_order).selectinload(RepairOrder.vehicle))
        .where(Invoice.id == body.invoice_id)
    )
    invoice = result.scalar_one_or_none()

    if not invoice:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found")

    if invoice.repair_order.customer_id != current_user.customer_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    if invoice.status == InvoiceStatus.CANCELLED:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Voided invoices cannot be paid")

    # Get tenant to check for Stripe Connect
    tenant_result = await db.execute(select(Tenant).where(Tenant.id == invoice.tenant_id))
    tenant = tenant_result.scalar_one_or_none()

    # Load customer for confirmation email
    customer_result = await db.execute(
        select(Customer).where(Customer.id == current_user.customer_id)
    )
    customer = customer_result.scalar_one_or_none()
    
    # Verify payment intent status with Stripe
    # If using Connect, retrieve from connected account
    try:
        retrieve_params = {}
        if tenant and tenant.stripe_account_id and tenant.stripe_onboarding_complete:
            retrieve_params["stripe_account"] = tenant.stripe_account_id
        payment_intent = stripe.PaymentIntent.retrieve(body.payment_intent_id, **retrieve_params)
    except stripe.error.InvalidRequestError as e:
        logger.warning("stripe_retrieve_payment_intent_failed", payment_intent_id=body.payment_intent_id, error=str(e))
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid payment intent")
    except stripe.error.StripeError as e:
        logger.error("stripe_retrieve_payment_intent_error", payment_intent_id=body.payment_intent_id, error=str(e))
        record_payment_error(error_type=type(e).__name__, provider="stripe")
        raise
    
    if payment_intent.status != "succeeded":
        logger.warning(
            "payment_not_succeeded",
            invoice_id=str(invoice.id),
            payment_intent_id=body.payment_intent_id,
            status=payment_intent.status,
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Payment not successful. Status: {payment_intent.status}",
        )
    
    # Verify this payment intent is for this invoice
    if payment_intent.metadata.get("invoice_id") != str(invoice.id):
        logger.warning(
            "payment_intent_mismatch",
            invoice_id=str(invoice.id),
            payment_intent_invoice_id=payment_intent.metadata.get("invoice_id"),
        )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Payment intent mismatch")
    
    await finalize_stripe_invoice_payment(
        db=db,
        invoice=invoice,
        order=invoice.repair_order,
        customer=customer,
        tenant=tenant,
        vehicle=invoice.repair_order.vehicle,
        payment_intent=payment_intent,
        payment_note=PORTAL_PAYMENT_NOTE,
    )
    
    return {
        "status": "success",
        "message": "Payment confirmed",
        "payment_note": PORTAL_PAYMENT_NOTE,
    }


@router.post("/record-manual", response_model=ManualPaymentResponse)
async def record_manual_payment(
    body: ManualPaymentRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Record a manual payment (cash, zelle, check, etc.) - staff only"""
    # Only garage staff can record manual payments
    if current_user.role not in [UserRole.GARAGE_OWNER, UserRole.GARAGE_ADMIN, UserRole.RECEPTIONIST]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Staff access required")
    
    # Validate payment method
    method_map = {
        'cash': PaymentMethodEnum.CASH,
        'zelle': PaymentMethodEnum.ZELLE,
        'check': PaymentMethodEnum.CHECK,
        'ach': PaymentMethodEnum.ACH,
        'fleet_payment': PaymentMethodEnum.FLEET_PAYMENT,
        'other': PaymentMethodEnum.OTHER,
    }
    if body.method not in method_map:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid payment method: {body.method}")

    payment_provider, reference_number, authorization_number, payment_notes = (
        _normalized_manual_payment_details(body)
    )
    
    # Get invoice (with repair order + vehicle eagerly loaded)
    result = await db.execute(
        select(Invoice)
        .options(selectinload(Invoice.repair_order).selectinload(RepairOrder.vehicle))
        .where(Invoice.id == body.invoice_id, Invoice.tenant_id == current_user.tenant_id)
    )
    invoice = result.scalar_one_or_none()
    
    if not invoice:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found")
    
    if invoice.status == InvoiceStatus.PAID:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invoice already paid")
    if invoice.status == InvoiceStatus.CANCELLED:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Voided invoices cannot be paid")

    tenant_result = await db.execute(select(Tenant).where(Tenant.id == invoice.tenant_id))
    tenant = tenant_result.scalar_one_or_none()

    # Optional walk-in capture/enrichment for Zelle payments
    customer_result = await db.execute(
        select(Customer).where(
            and_(
                Customer.id == invoice.repair_order.customer_id,
                Customer.tenant_id == current_user.tenant_id,
            )
        )
    )
    customer = customer_result.scalar_one_or_none()

    sender_email = _normalize_email(body.zelle_sender_email)
    sender_phone = _normalize_phone(body.zelle_sender_phone)
    should_update_from_sender = (
        body.method == "zelle"
        and body.update_customer_from_sender
        and (sender_email is not None or sender_phone is not None)
        and customer is not None
    )

    warning_message: Optional[str] = None

    if should_update_from_sender:
        if sender_email:
            # Keep tenant-scoped customer emails unique during enrichment.
            existing_result = await db.execute(
                select(Customer).where(
                    and_(
                        Customer.tenant_id == current_user.tenant_id,
                        Customer.email == sender_email,
                        Customer.id != customer.id,
                    )
                )
            )
            email_conflict = existing_result.scalar_one_or_none()
            if email_conflict:
                warning_message = (
                    "Sender email was not applied because it already belongs to another customer in this garage."
                )
                logger.warning(
                    "zelle_sender_email_conflict",
                    invoice_id=str(invoice.id),
                    customer_id=str(customer.id),
                    conflicting_customer_id=str(email_conflict.id),
                    sender_email=sender_email,
                )
            else:
                customer.email = sender_email

        if sender_phone:
            customer.phone = sender_phone

        customer.source = "zelle"

    elif body.method == "zelle" and customer and _is_placeholder_walkin_customer(customer):
        # Track source when a walk-in record is paid via Zelle, even if sender details are omitted.
        customer.source = "zelle"
    
    # Clear pending-Zelle tracking now that staff is explicitly recording payment.
    invoice.zelle_pending_submitted_at = None
    invoice.zelle_pending_sender_email = None
    invoice.zelle_pending_sender_phone = None
    invoice.zelle_pending_last_reminder_at = None
    invoice.zelle_pending_reminder_count = 0

    # Update invoice status
    invoice.status = InvoiceStatus.PAID
    invoice.paid_at = datetime.now(timezone.utc)
    
    # Update repair order status
    invoice.repair_order.status = RepairOrderStatus.PAID
    
    # Create payment record. Manual methods (cash, Zelle, checks, ACH, and fleet
    # instruments) are
    # not card payments, so they don't incur the card processing fee — the amount
    # actually collected is the invoice total minus that fee. Only Stripe (card)
    # collects the full total_amount.
    collected_amount = invoice.total_amount - (invoice.service_fee_amount or Decimal("0.00"))
    payment_number = await allocate_next_payment_number(db, invoice.tenant_id)
    payment = Payment(
        tenant_id=invoice.tenant_id,
        invoice_id=invoice.id,
        payment_number=payment_number,
        amount=collected_amount,
        method=method_map[body.method],
        status=PaymentStatus.COMPLETED,
        notes=payment_notes,
        payment_provider=payment_provider,
        reference_number=reference_number,
        authorization_number=authorization_number,
        recorded_by_user_id=current_user.id,
    )
    db.add(payment)
    
    await db.commit()
    await db.refresh(invoice)
    await db.refresh(invoice.repair_order)
    
    # Broadcast WebSocket updates
    await broadcast_payment_received(
        tenant_id=str(invoice.tenant_id),
        customer_id=str(invoice.repair_order.customer_id),
        invoice_id=str(invoice.id),
        order_id=str(invoice.repair_order_id),
    )
    await broadcast_repair_order_update(
        tenant_id=str(invoice.tenant_id),
        customer_id=str(invoice.repair_order.customer_id),
        order_id=str(invoice.repair_order_id),
        order_number=invoice.repair_order.order_number,
        status=invoice.repair_order.status.value,
        updated_at=invoice.repair_order.updated_at.isoformat() if invoice.repair_order.updated_at else None,
    )
    
    # Record successful payment metric
    record_payment(status="success", payment_method=body.method, tenant_id=str(invoice.tenant_id))
    logger.info(
        "manual_payment_recorded",
        invoice_id=str(invoice.id),
        method=body.method,
        amount=float(invoice.total_amount),
    )

    try:
        await send_invoice_payment_confirmation_email(
            db=db,
            invoice=invoice,
            order=invoice.repair_order,
            customer=customer,
            tenant=tenant,
            vehicle=invoice.repair_order.vehicle,
        )
    except Exception as exc:
        logger.warning(
            "invoice_paid_confirmation_email_failed",
            invoice_id=str(invoice.id),
            error=str(exc),
        )
    
    return {
        "status": "success",
        "message": f"Payment recorded as {body.method}",
        "warning": warning_message,
    }


@router.post("/zelle-pending/revert")
async def revert_pending_zelle(
    body: RevertPendingZelleRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Clear pending-Zelle state when staff determines no payment was received."""
    if current_user.role not in [UserRole.GARAGE_OWNER, UserRole.GARAGE_ADMIN, UserRole.RECEPTIONIST]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Staff access required")

    result = await db.execute(
        select(Invoice)
        .options(selectinload(Invoice.repair_order))
        .where(
            and_(
                Invoice.id == body.invoice_id,
                Invoice.tenant_id == current_user.tenant_id,
            )
        )
    )
    invoice = result.scalar_one_or_none()
    if not invoice:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found")
    if invoice.status == InvoiceStatus.PAID:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invoice is already paid")
    if not invoice.zelle_pending_submitted_at:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invoice is not pending Zelle confirmation")

    invoice.zelle_pending_submitted_at = None
    invoice.zelle_pending_sender_email = None
    invoice.zelle_pending_sender_phone = None
    invoice.zelle_pending_last_reminder_at = None
    invoice.zelle_pending_reminder_count = 0
    if body.reason:
        reason = body.reason.strip()
        if reason:
            existing_notes = (invoice.notes or "").strip()
            prefix = f"[Zelle pending cleared] {reason}"
            invoice.notes = f"{existing_notes}\n{prefix}".strip() if existing_notes else prefix

    await db.commit()
    await db.refresh(invoice)
    await db.refresh(invoice.repair_order)

    await broadcast_repair_order_update(
        tenant_id=str(invoice.tenant_id),
        customer_id=str(invoice.repair_order.customer_id),
        order_id=str(invoice.repair_order_id),
        order_number=invoice.repair_order.order_number,
        status=invoice.repair_order.status.value,
        updated_at=invoice.repair_order.updated_at.isoformat() if invoice.repair_order.updated_at else None,
    )

    return {"status": "success", "message": "Pending Zelle status cleared"}


@router.post("/submit-zelle", response_model=SubmitCustomerZellePaymentResponse)
@limiter.limit("5/minute")
async def submit_customer_zelle_payment(
    request: Request,
    body: SubmitCustomerZellePaymentRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Mark an invoice as pending Zelle confirmation from the customer portal."""
    if current_user.role != UserRole.CUSTOMER or not current_user.customer_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Customer access required")

    result = await db.execute(
        select(Invoice)
        .options(selectinload(Invoice.repair_order))
        .where(Invoice.id == body.invoice_id)
    )
    invoice = result.scalar_one_or_none()
    if not invoice:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found")
    if invoice.repair_order.customer_id != current_user.customer_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    if invoice.status == InvoiceStatus.PAID:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invoice already paid")
    if invoice.status == InvoiceStatus.CANCELLED:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Voided invoices cannot be paid")

    was_pending = invoice.pending_zelle_confirmation
    sender_email = _normalize_email(str(body.sender_email) if body.sender_email else current_user.email)
    sender_phone = _normalize_phone(body.sender_phone or current_user.phone)
    notes = body.notes.strip() if body.notes else None
    zelle_amount = invoice.total_amount - (invoice.service_fee_amount or 0)

    invoice.zelle_pending_submitted_at = datetime.now(timezone.utc)
    invoice.zelle_pending_sender_email = sender_email
    invoice.zelle_pending_sender_phone = sender_phone
    invoice.zelle_pending_last_reminder_at = None
    invoice.zelle_pending_reminder_count = 0
    if notes:
        existing_notes = (invoice.notes or "").strip()
        note_line = f"[Customer portal Zelle submit] {notes}"
        invoice.notes = f"{existing_notes}\n{note_line}".strip() if existing_notes else note_line

    await db.commit()
    await db.refresh(invoice)
    await db.refresh(invoice.repair_order)

    customer_name = f"{current_user.first_name} {current_user.last_name}".strip() or "Customer"
    if not was_pending:
        try:
            await send_pending_zelle_submission_alert(
                db=db,
                tenant_id=invoice.tenant_id,
                order_id=invoice.repair_order.id,
                order_number=invoice.repair_order.order_number,
                invoice_number=invoice.invoice_number,
                customer_name=customer_name,
                amount=zelle_amount,
                source_label="customer portal",
                sender_email=sender_email,
                sender_phone=sender_phone,
            )
        except Exception as exc:
            logger.warning(
                "pending_zelle_submission_alert_failed",
                invoice_id=str(invoice.id),
                source="customer_portal",
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
        "customer_portal_zelle_submitted",
        invoice_id=str(invoice.id),
        customer_id=str(current_user.customer_id),
    )

    return SubmitCustomerZellePaymentResponse(
        status="success",
        message="Zelle payment marked as submitted. Shop staff will confirm receipt.",
        pending_zelle_confirmation=invoice.pending_zelle_confirmation,
    )


@router.get("/zelle-info/{invoice_id}", response_model=ZelleInfoResponse)
async def get_zelle_info(
    invoice_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Get Zelle payment info for an invoice's garage"""
    # Get invoice to find tenant
    result = await db.execute(
        select(Invoice)
        .options(selectinload(Invoice.repair_order))
        .where(Invoice.id == invoice_id)
    )
    invoice = result.scalar_one_or_none()
    
    if not invoice:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found")
    
    # Verify access - customer must own invoice or be staff
    if current_user.role == UserRole.CUSTOMER:
        if invoice.repair_order.customer_id != current_user.customer_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    elif current_user.tenant_id != invoice.tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    
    # Get tenant Zelle info
    result = await db.execute(select(Tenant).where(Tenant.id == invoice.tenant_id))
    tenant = result.scalar_one_or_none()
    
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shop not found")
    
    return ZelleInfoResponse(
        zelle_email=tenant.zelle_email,
        zelle_phone=tenant.zelle_phone,
        zelle_qr_image=tenant.zelle_qr_image,
        garage_name=tenant.name,
        stripe_payments_available=bool(
            tenant.stripe_account_id and tenant.stripe_onboarding_complete
        ),
    )
