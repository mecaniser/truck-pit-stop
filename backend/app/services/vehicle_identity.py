"""Vehicle identity, account relationships, and fleet membership helpers."""

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.customer import Customer
from app.db.models.vehicle import Vehicle
from app.db.models.vehicle_relationship import FleetMembership, VehicleCustomerRelationship


VEHICLE_RELATIONSHIP_TYPES = {"owner", "operator", "default_payer"}


def normalize_vin(value: Optional[str]) -> Optional[str]:
    normalized = (value or "").strip().upper()
    return normalized or None


async def find_vehicle_by_vin(
    db: AsyncSession,
    tenant_id: UUID,
    vin: Optional[str],
    *,
    exclude_vehicle_id: Optional[UUID] = None,
) -> Optional[Vehicle]:
    normalized = normalize_vin(vin)
    # Short chassis/serial references are useful search terms but are not
    # globally reliable physical identities. Only a valid-length VIN blocks a
    # create/update.
    if not normalized or len(normalized) != 17:
        return None
    filters = [
        Vehicle.tenant_id == tenant_id,
        Vehicle.deleted_at.is_(None),
        func.upper(Vehicle.vin) == normalized,
    ]
    if exclude_vehicle_id:
        filters.append(Vehicle.id != exclude_vehicle_id)
    return (await db.execute(select(Vehicle).where(*filters))).scalars().first()


async def ensure_vehicle_relationship(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    vehicle_id: UUID,
    customer_id: UUID,
    relationship_type: str,
    is_primary: bool = False,
) -> VehicleCustomerRelationship:
    if relationship_type not in VEHICLE_RELATIONSHIP_TYPES:
        raise ValueError(f"Unsupported vehicle relationship: {relationship_type}")
    existing = (await db.execute(
        select(VehicleCustomerRelationship).where(
            VehicleCustomerRelationship.tenant_id == tenant_id,
            VehicleCustomerRelationship.vehicle_id == vehicle_id,
            VehicleCustomerRelationship.customer_id == customer_id,
            VehicleCustomerRelationship.relationship_type == relationship_type,
            VehicleCustomerRelationship.effective_to.is_(None),
            VehicleCustomerRelationship.deleted_at.is_(None),
        )
    )).scalars().first()
    if existing:
        if is_primary and not existing.is_primary:
            existing.is_primary = True
        return existing
    relationship = VehicleCustomerRelationship(
        tenant_id=tenant_id,
        vehicle_id=vehicle_id,
        customer_id=customer_id,
        relationship_type=relationship_type,
        is_primary=is_primary,
    )
    db.add(relationship)
    return relationship


async def seed_vehicle_account_relationships(
    db: AsyncSession, vehicle: Vehicle, customer: Customer
) -> None:
    """Record the compatibility customer as initial owner and default payer."""
    await ensure_vehicle_relationship(
        db,
        tenant_id=vehicle.tenant_id,
        vehicle_id=vehicle.id,
        customer_id=customer.id,
        relationship_type="owner",
        is_primary=True,
    )
    await ensure_vehicle_relationship(
        db,
        tenant_id=vehicle.tenant_id,
        vehicle_id=vehicle.id,
        customer_id=customer.id,
        relationship_type="default_payer",
        is_primary=True,
    )


async def ensure_fleet_membership(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    vehicle_id: UUID,
    fleet_customer_id: UUID,
) -> FleetMembership:
    existing = (await db.execute(
        select(FleetMembership).where(
            FleetMembership.tenant_id == tenant_id,
            FleetMembership.vehicle_id == vehicle_id,
            FleetMembership.fleet_customer_id == fleet_customer_id,
            FleetMembership.effective_to.is_(None),
            FleetMembership.deleted_at.is_(None),
        )
    )).scalars().first()
    if existing:
        return existing
    membership = FleetMembership(
        tenant_id=tenant_id,
        vehicle_id=vehicle_id,
        fleet_customer_id=fleet_customer_id,
    )
    db.add(membership)
    await ensure_vehicle_relationship(
        db,
        tenant_id=tenant_id,
        vehicle_id=vehicle_id,
        customer_id=fleet_customer_id,
        relationship_type="operator",
    )
    return membership


async def end_fleet_membership(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    vehicle_id: UUID,
    fleet_customer_id: UUID,
) -> bool:
    membership = (await db.execute(
        select(FleetMembership).where(
            FleetMembership.tenant_id == tenant_id,
            FleetMembership.vehicle_id == vehicle_id,
            FleetMembership.fleet_customer_id == fleet_customer_id,
            FleetMembership.effective_to.is_(None),
            FleetMembership.deleted_at.is_(None),
        )
    )).scalars().first()
    if not membership:
        return False
    membership.effective_to = datetime.now(timezone.utc)
    return True


async def sync_customer_fleet_memberships(
    db: AsyncSession, customer: Customer, *, enabled: bool
) -> None:
    """Enroll/end the customer's compatibility vehicles as one atomic fleet."""
    if enabled:
        vehicle_ids = list((await db.execute(
            select(Vehicle.id).where(
                Vehicle.tenant_id == customer.tenant_id,
                Vehicle.customer_id == customer.id,
                Vehicle.deleted_at.is_(None),
            )
        )).scalars().all())
        for vehicle_id in vehicle_ids:
            await ensure_fleet_membership(
                db,
                tenant_id=customer.tenant_id,
                vehicle_id=vehicle_id,
                fleet_customer_id=customer.id,
            )
        return

    now = datetime.now(timezone.utc)
    memberships = list((await db.execute(
        select(FleetMembership).where(
            FleetMembership.tenant_id == customer.tenant_id,
            FleetMembership.fleet_customer_id == customer.id,
            FleetMembership.effective_to.is_(None),
            FleetMembership.deleted_at.is_(None),
        )
    )).scalars().all())
    for membership in memberships:
        membership.effective_to = now
