"""Helpers for the garage's internal fleet "house account".

Each tenant owns exactly one internal-fleet customer. Vehicles attached to it are
the garage's own trucks, and repair orders against it are priced at internal cost
(see ``app.services.price_build_service``) and never invoiced to a paying customer.
"""
import math
from datetime import date, timedelta
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.customer import Customer
from app.db.models.tenant import Tenant


# Assumed average daily mileage for a fleet truck, used to project the PM due
# date from the remaining miles so the date and odometer triggers stay in sync.
PM_AVG_MILES_PER_DAY = 600


def _company_identity(value: Optional[str]) -> str:
    """Normalize a company name for the configured internal-fleet match."""
    if not value:
        return ""
    ignored_tokens = {"llc", "inc", "ltd", "corp", "co", "company"}
    return " ".join(
        token for token in "".join(char.lower() if char.isalnum() else " " for char in value).split()
        if token not in ignored_tokens
    )


def uses_internal_fleet_pricing(customer: Optional[Customer], tenant: Tenant) -> bool:
    """Whether work billed to ``customer`` should use the shop's internal rates.

    The dedicated house account remains the primary source of truth. Some shops
    instead use their configured operating authority (for example, "77 Cargo")
    as that account, so recognize it only when it is both the configured default
    authority and matches the tenant's internal-fleet company name.
    """
    if not customer:
        return False
    if customer.is_internal_fleet:
        return True
    return bool(
        tenant.default_fleet_authority_customer_id == customer.id
        and _company_identity(customer.company_name) == _company_identity(tenant.fleet_company_name)
        and _company_identity(tenant.fleet_company_name)
    )


def project_pm_due_date(
    next_pm_miles: Optional[int],
    current_odometer: Optional[int],
    *,
    from_date: Optional[date] = None,
) -> Optional[date]:
    """Estimate the PM due date from the mileage target, so the date and the
    odometer trigger describe the same event instead of drifting apart.

    date = from_date + ceil(miles_remaining / PM_AVG_MILES_PER_DAY) days.
    Overdue-on-mileage (remaining <= 0) projects to today (from_date). Returns
    None when there's no mileage target to project from.
    """
    if next_pm_miles is None:
        return None
    base_date = from_date or date.today()
    remaining = next_pm_miles - (current_odometer or 0)
    if remaining <= 0:
        return base_date
    days = math.ceil(remaining / PM_AVG_MILES_PER_DAY)
    return base_date + timedelta(days=days)


def advance_vehicle_pm(vehicle, base_odometer: Optional[int], completed_on: Optional[date] = None) -> None:
    """Roll the truck's next PM forward after a PM work order completes — both the
    mileage target and the scheduled date. The date is projected from the new
    mileage target (at PM_AVG_MILES_PER_DAY) so the two triggers stay consistent."""
    base = base_odometer or vehicle.mileage or 0
    vehicle.next_pm_miles = base + (vehicle.pm_interval_miles or 25000)
    # Project from the base odometer we just serviced at (miles_remaining = interval).
    vehicle.pm_due_date = project_pm_due_date(
        vehicle.next_pm_miles, base, from_date=(completed_on or date.today())
    )


def fleet_display_name(customer, fleet_company_name: Optional[str]) -> str:
    """Customer display name for a repair order.

    This is a heavy-duty shop: the work belongs to a carrier, so the company
    name is the identifier that matters and the contact's own name is
    secondary. Company name first, personal name only when there is no company
    on the record — the same rule the customer ledger already applies.

    Internal fleet ROs are the exception ahead of that: their customer is the
    tenant's house account, whose generic placeholder name should never show,
    so the configured fleet company name wins.
    """
    if getattr(customer, "is_internal_fleet", False) and fleet_company_name:
        return fleet_company_name
    company = (getattr(customer, "company_name", None) or "").strip()
    if company:
        return company
    return f"{customer.first_name} {customer.last_name}".strip()


def fleet_labor_uses_customer_rate(order) -> bool:
    """Whether this fleet order bills labor at the tenant's normal rate.

    Fleet work remains operationally internal even when it is invoiced. The
    order-level snapshot, rather than the mutable truck setting, is the source
    of truth once work has begun.
    """
    return bool(
        getattr(order, "is_internal", False)
        and getattr(order, "bill_labor_at_customer_rate", False)
    )


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
