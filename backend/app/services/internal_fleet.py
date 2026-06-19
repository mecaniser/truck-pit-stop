"""Helpers for the garage's internal fleet "house account".

Each tenant owns exactly one internal-fleet customer. Vehicles attached to it are
the garage's own trucks, and repair orders against it are priced at internal cost
(see ``app.services.price_build_service``) and never invoiced to a paying customer.
"""
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.customer import Customer


async def get_internal_fleet_customer(
    db: AsyncSession, tenant_id: UUID
) -> Optional[Customer]:
    """Return the tenant's internal-fleet house account, or None if missing."""
    result = await db.execute(
        select(Customer).where(
            Customer.tenant_id == tenant_id,
            Customer.is_internal_fleet.is_(True),
            Customer.deleted_at.is_(None),
        )
    )
    return result.scalars().first()


async def ensure_internal_fleet_customer(
    db: AsyncSession, tenant_id: UUID
) -> Customer:
    """Get-or-create the tenant's internal-fleet house account.

    Idempotent: safe to call on every tenant creation. Does not commit — the caller
    owns the surrounding transaction.
    """
    existing = await get_internal_fleet_customer(db, tenant_id)
    if existing:
        return existing

    customer = Customer(
        tenant_id=tenant_id,
        first_name="Internal",
        last_name="Fleet",
        company_name="House Account",
        email=f"fleet+{tenant_id}@internal.local",
        is_internal_fleet=True,
    )
    db.add(customer)
    await db.flush()
    return customer
