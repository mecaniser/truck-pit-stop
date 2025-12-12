from typing import Optional
from decimal import Decimal
import stripe
from app.core.config import settings

stripe.api_key = settings.STRIPE_SECRET_KEY


def create_payment_intent(
    amount: Decimal,
    currency: str = "usd",
    customer_id: Optional[str] = None,
    metadata: Optional[dict] = None,
) -> stripe.PaymentIntent:
    """Create a Stripe payment intent"""
    
    intent_data = {
        "amount": int(amount * 100),  # Convert to cents
        "currency": currency,
    }
    
    if customer_id:
        intent_data["customer"] = customer_id
    
    if metadata:
        intent_data["metadata"] = metadata
    
    return stripe.PaymentIntent.create(**intent_data)


def retrieve_payment_intent(payment_intent_id: str) -> stripe.PaymentIntent:
    """Retrieve a payment intent"""
    return stripe.PaymentIntent.retrieve(payment_intent_id)


def confirm_payment_intent(payment_intent_id: str) -> stripe.PaymentIntent:
    """Confirm a payment intent"""
    return stripe.PaymentIntent.confirm(payment_intent_id)


