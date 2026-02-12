import secrets
from datetime import datetime, timezone
from urllib.parse import urlencode
from typing import Optional

from app.core.config import settings
from app.core.redis import store_invoice_access_token, store_portal_enrollment_token
from app.db.models.customer import Customer
from app.db.models.invoice import Invoice
from app.db.models.repair_order import RepairOrder


INVOICE_ACCESS_TOKEN_TTL_SECONDS = 7 * 24 * 60 * 60  # 7 days
PORTAL_ENROLLMENT_TOKEN_TTL_SECONDS = 24 * 60 * 60  # 24 hours


async def generate_invoice_access_token(
    invoice: Invoice,
    order: RepairOrder,
    customer: Customer,
) -> str:
    """Generate and persist an invoice access token."""
    token = secrets.token_urlsafe(48)
    payload = {
        "invoice_id": str(invoice.id),
        "repair_order_id": str(order.id),
        "customer_id": str(customer.id),
        "tenant_id": str(invoice.tenant_id),
        "email": customer.email,
        "issued_at": datetime.now(timezone.utc).isoformat(),
    }
    await store_invoice_access_token(token, payload, INVOICE_ACCESS_TOKEN_TTL_SECONDS)
    return token


async def generate_invoice_access_link(
    invoice: Invoice,
    order: RepairOrder,
    customer: Customer,
    shop_name: Optional[str] = None,
    shop_phone: Optional[str] = None,
    shop_email: Optional[str] = None,
) -> str:
    """Generate a full frontend URL for tokenized invoice access."""
    token = await generate_invoice_access_token(invoice=invoice, order=order, customer=customer)
    base_url = f"{settings.FRONTEND_URL}/invoice/{token}"
    query_params = {}
    if shop_name:
        query_params["shop_name"] = shop_name
    if shop_phone:
        query_params["shop_phone"] = shop_phone
    if shop_email:
        query_params["shop_email"] = shop_email

    if not query_params:
        return base_url

    return f"{base_url}?{urlencode(query_params)}"


async def generate_portal_enrollment_token(
    invoice: Invoice,
    order: RepairOrder,
    customer: Customer,
) -> str:
    """Generate a short-lived one-time portal enrollment token."""
    token = secrets.token_urlsafe(48)
    payload = {
        "invoice_id": str(invoice.id),
        "repair_order_id": str(order.id),
        "customer_id": str(customer.id),
        "tenant_id": str(invoice.tenant_id),
        "email": customer.email,
        "issued_at": datetime.now(timezone.utc).isoformat(),
        "purpose": "portal_enrollment",
    }
    await store_portal_enrollment_token(token, payload, PORTAL_ENROLLMENT_TOKEN_TTL_SECONDS)
    return token
