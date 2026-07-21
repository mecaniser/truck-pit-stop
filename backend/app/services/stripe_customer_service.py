"""Stripe Customer helpers for direct charges on connected merchant accounts."""
from __future__ import annotations

from typing import Any

import stripe
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.customer import Customer


def _stripe_value(value: Any, key: str, default: Any = None) -> Any:
    return value.get(key, default) if isinstance(value, dict) else getattr(value, key, default)


def _customer_name(customer: Customer) -> str:
    return customer.company_name or f"{customer.first_name} {customer.last_name}".strip()


async def ensure_connected_stripe_customer(
    db: AsyncSession,
    customer: Customer,
    connected_account_id: str,
) -> str:
    """Create or refresh the payer record inside the tenant's Stripe account.

    Stripe Customers are account-scoped. A legacy customer ID created on the
    platform account cannot be attached to a direct charge, so recreate it in
    the connected account when necessary.
    """
    customer_params = {
        "email": customer.email,
        "name": _customer_name(customer),
        "metadata": {
            "dieselbridge_customer_id": str(customer.id),
            "dieselbridge_tenant_id": str(customer.tenant_id),
        },
        "stripe_account": connected_account_id,
    }

    if customer.stripe_customer_id:
        try:
            stripe.Customer.modify(customer.stripe_customer_id, **customer_params)
            return customer.stripe_customer_id
        except stripe.error.InvalidRequestError as exc:
            # The local ID belongs to an earlier connected account or the
            # merchant removed it in Stripe. Replace it below.
            if getattr(exc, "code", None) != "resource_missing":
                raise

    stripe_customer = stripe.Customer.create(**customer_params)
    stripe_customer_id = _stripe_value(stripe_customer, "id")
    if not stripe_customer_id:
        raise ValueError("Stripe did not return a customer ID")

    customer.stripe_customer_id = stripe_customer_id
    await db.commit()
    return stripe_customer_id
