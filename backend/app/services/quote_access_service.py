import secrets
from datetime import datetime, timezone

from app.core.redis import store_quote_portal_enrollment_token
from app.db.models.customer import Customer
from app.db.models.quote import Quote
from app.db.models.repair_order import RepairOrder


QUOTE_PORTAL_ENROLLMENT_TOKEN_TTL_SECONDS = 24 * 60 * 60  # 24 hours


async def generate_quote_portal_enrollment_token(
    quote: Quote,
    order: RepairOrder,
    customer: Customer,
) -> str:
    """Generate and persist a short-lived one-time quote portal enrollment token."""
    token = secrets.token_urlsafe(48)
    payload = {
        "quote_id": str(quote.id),
        "repair_order_id": str(order.id),
        "customer_id": str(customer.id),
        "tenant_id": str(order.tenant_id),
        "email": customer.email,
        "issued_at": datetime.now(timezone.utc).isoformat(),
        "purpose": "quote_portal_enrollment",
    }
    await store_quote_portal_enrollment_token(token, payload, QUOTE_PORTAL_ENROLLMENT_TOKEN_TTL_SECONDS)
    return token
