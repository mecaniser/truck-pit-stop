from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
import stripe
from app.core.config import settings
from app.core.dependencies import get_db, get_current_active_user
from app.db.models.user import User, UserRole
from app.db.models.customer import Customer

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
