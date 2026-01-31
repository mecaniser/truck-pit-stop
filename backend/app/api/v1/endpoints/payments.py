from typing import List, Optional
from uuid import UUID
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from pydantic import BaseModel
from decimal import Decimal
import stripe
from app.core.config import settings
from app.core.dependencies import get_db, get_current_active_user
from app.db.models.user import User, UserRole
from app.db.models.customer import Customer
from app.db.models.invoice import Invoice, InvoiceStatus
from app.db.models.repair_order import RepairOrder, RepairOrderStatus
from app.db.models.payment import Payment, PaymentMethod as PaymentMethodEnum, PaymentStatus


async def generate_payment_number(db: AsyncSession, tenant_id: UUID) -> str:
    result = await db.execute(
        select(func.count(Payment.id)).where(Payment.tenant_id == tenant_id)
    )
    count = result.scalar() or 0
    return f"PAY-{str(tenant_id).replace('-', '').upper()[:8]}-{count + 1:06d}"

stripe.api_key = settings.STRIPE_SECRET_KEY

router = APIRouter()


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


class ConfirmPaymentRequest(BaseModel):
    invoice_id: UUID
    payment_intent_id: str


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
    if not customer.stripe_customer_id:
        stripe_customer = stripe.Customer.create(
            email=customer.email,
            name=f"{customer.first_name} {customer.last_name}",
            metadata={"customer_id": str(customer.id)},
        )
        customer.stripe_customer_id = stripe_customer.id
        await db.commit()
    
    # Create SetupIntent
    setup_intent = stripe.SetupIntent.create(
        customer=customer.stripe_customer_id,
        payment_method_types=["card"],
    )
    
    return SetupIntentResponse(client_secret=setup_intent.client_secret)


@router.get("/methods", response_model=List[PaymentMethodResponse])
async def list_payment_methods(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """List customer's saved payment methods"""
    if current_user.role != UserRole.CUSTOMER or not current_user.customer_id:
        return []
    
    # Get customer record
    result = await db.execute(select(Customer).where(Customer.id == current_user.customer_id))
    customer = result.scalar_one_or_none()
    
    if not customer or not customer.stripe_customer_id:
        return []
    
    # Get payment methods from Stripe
    payment_methods = stripe.PaymentMethod.list(
        customer=customer.stripe_customer_id,
        type="card",
    )
    
    # Get default payment method
    stripe_customer = stripe.Customer.retrieve(customer.stripe_customer_id)
    default_pm_id = stripe_customer.invoice_settings.default_payment_method
    
    return [
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
    except stripe.error.InvalidRequestError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payment method not found")


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
    except stripe.error.InvalidRequestError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payment method not found")


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
        .options(selectinload(Invoice.repair_order))
        .where(Invoice.id == body.invoice_id)
    )
    invoice = result.scalar_one_or_none()
    
    if not invoice:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found")
    
    # Verify customer owns this invoice
    if invoice.repair_order.customer_id != current_user.customer_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    
    if invoice.status == InvoiceStatus.PAID:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invoice already paid")
    
    # Get customer for Stripe customer ID
    result = await db.execute(select(Customer).where(Customer.id == current_user.customer_id))
    customer = result.scalar_one_or_none()
    
    # Create or get Stripe customer
    stripe_customer_id = None
    if customer:
        if not customer.stripe_customer_id:
            stripe_customer = stripe.Customer.create(
                email=customer.email,
                name=f"{customer.first_name} {customer.last_name}",
                metadata={"customer_id": str(customer.id)},
            )
            customer.stripe_customer_id = stripe_customer.id
            await db.commit()
        stripe_customer_id = customer.stripe_customer_id
    
    # Create PaymentIntent
    amount_cents = int(invoice.total_amount * 100)
    intent_params = {
        "amount": amount_cents,
        "currency": "usd",
        "metadata": {
            "invoice_id": str(invoice.id),
            "invoice_number": invoice.invoice_number,
        },
        "automatic_payment_methods": {"enabled": True},
    }
    if stripe_customer_id:
        intent_params["customer"] = stripe_customer_id
    
    payment_intent = stripe.PaymentIntent.create(**intent_params)
    
    return PaymentIntentResponse(
        client_secret=payment_intent.client_secret,
        payment_intent_id=payment_intent.id,
        amount=invoice.total_amount,
    )


@router.post("/confirm-payment")
async def confirm_payment(
    body: ConfirmPaymentRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Confirm payment was successful and update invoice/repair order status"""
    if current_user.role != UserRole.CUSTOMER or not current_user.customer_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    
    # Get invoice
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
    
    # Verify payment intent status with Stripe
    try:
        payment_intent = stripe.PaymentIntent.retrieve(body.payment_intent_id)
    except stripe.error.InvalidRequestError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid payment intent")
    
    if payment_intent.status != "succeeded":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Payment not successful. Status: {payment_intent.status}",
        )
    
    # Verify this payment intent is for this invoice
    if payment_intent.metadata.get("invoice_id") != str(invoice.id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Payment intent mismatch")
    
    # Update invoice status
    invoice.status = InvoiceStatus.PAID
    invoice.paid_at = datetime.utcnow()
    
    # Update repair order status
    invoice.repair_order.status = RepairOrderStatus.PAID
    
    # Create payment record
    payment_number = await generate_payment_number(db, invoice.tenant_id)
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
    
    return {"status": "success", "message": "Payment confirmed"}
