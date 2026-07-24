"""Vehicle identity, account relationships, and fleet membership helpers."""

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import and_, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.customer import Customer
from app.db.models.repair_order import RepairOrder
from app.db.models.vehicle import Vehicle
from app.db.models.vehicle_relationship import FleetMembership, VehicleCustomerRelationship


VEHICLE_RELATIONSHIP_TYPES = {"owner", "operator", "default_payer"}


async def duplicate_vin_detail(
    db: AsyncSession,
    vehicle: Vehicle,
    *,
    include_vehicle: bool = True,
) -> dict:
    """Describe an existing VIN match without exposing the internal vehicle ID."""
    detail = {
        "code": "duplicate_vin",
        "message": "This VIN is already assigned to an existing truck.",
    }
    if not include_vehicle:
        return detail

    customer = (await db.execute(
        select(Customer).where(Customer.id == vehicle.customer_id)
    )).scalar_one_or_none()
    customer_name = None
    if customer:
        customer_name = customer.company_name or f"{customer.first_name} {customer.last_name}".strip()

    relationship_rows = (await db.execute(
        select(VehicleCustomerRelationship, Customer)
        .join(Customer, Customer.id == VehicleCustomerRelationship.customer_id)
        .where(
            VehicleCustomerRelationship.vehicle_id == vehicle.id,
            VehicleCustomerRelationship.tenant_id == vehicle.tenant_id,
            VehicleCustomerRelationship.effective_to.is_(None),
            VehicleCustomerRelationship.deleted_at.is_(None),
            Customer.deleted_at.is_(None),
        )
        .order_by(
            VehicleCustomerRelationship.is_primary.desc(),
            VehicleCustomerRelationship.effective_from.desc(),
        )
    )).all()
    role_names: dict[str, str] = {}
    for relationship, relationship_customer in relationship_rows:
        role_names.setdefault(
            relationship.relationship_type,
            relationship_customer.company_name
            or f"{relationship_customer.first_name} {relationship_customer.last_name}".strip(),
        )

    detail["vehicle"] = {
        "id": str(vehicle.id),
        "vin": vehicle.vin,
        "unit_number": vehicle.unit_number,
        "year": vehicle.year,
        "make": vehicle.make,
        "model": vehicle.model,
        "license_plate": vehicle.license_plate,
        "customer_id": str(vehicle.customer_id),
        "customer_name": customer_name,
        "owner_lessor_name": role_names.get("owner") or customer_name,
        "operating_authority_name": role_names.get("operator"),
        "default_invoice_recipient_name": role_names.get("default_payer"),
    }
    return detail


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
    # Legacy imports can contain more than one row for the same VIN. Prefer the
    # truck with real service history, then the most recently maintained row,
    # so a stale zero-history Fleet/House Account shell never wins a relink.
    service_count = select(func.count(RepairOrder.id)).where(
        RepairOrder.vehicle_id == Vehicle.id,
        RepairOrder.deleted_at.is_(None),
    ).scalar_subquery()
    return (await db.execute(
        select(Vehicle)
        .where(*filters)
        .order_by(service_count.desc(), Vehicle.updated_at.desc(), Vehicle.created_at.desc())
    )).scalars().first()


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
    active_memberships = list((await db.execute(
        select(FleetMembership).where(
            FleetMembership.tenant_id == tenant_id,
            FleetMembership.vehicle_id == vehicle_id,
            FleetMembership.effective_to.is_(None),
            FleetMembership.deleted_at.is_(None),
        )
    )).scalars().all())
    existing = next(
        (membership for membership in active_memberships if membership.fleet_customer_id == fleet_customer_id),
        None,
    )
    now = datetime.now(timezone.utc)
    for membership in active_memberships:
        if membership.fleet_customer_id != fleet_customer_id:
            membership.effective_to = now

    # One physical truck has one current operating fleet. Preserve previous
    # operators as dated history, but never let an older Fleet Board assignment
    # outrank the customer/operator selected now.
    previous_operators = list((await db.execute(
        select(VehicleCustomerRelationship).where(
            VehicleCustomerRelationship.tenant_id == tenant_id,
            VehicleCustomerRelationship.vehicle_id == vehicle_id,
            VehicleCustomerRelationship.relationship_type == "operator",
            VehicleCustomerRelationship.customer_id != fleet_customer_id,
            VehicleCustomerRelationship.effective_to.is_(None),
            VehicleCustomerRelationship.deleted_at.is_(None),
        )
    )).scalars().all())
    for relationship in previous_operators:
        relationship.effective_to = now

    async def ensure_external_default_payer() -> None:
        """Replace only the legacy internal payer when an external fleet takes over.

        A real external payer (for example the leasing owner) is contractual and
        must not be overwritten merely because the truck changes operators.
        """
        fleet_is_internal = (await db.execute(select(Customer.is_internal_fleet).where(
            Customer.id == fleet_customer_id,
            Customer.tenant_id == tenant_id,
            Customer.deleted_at.is_(None),
        ))).scalar_one_or_none()
        if fleet_is_internal:
            return

        payer_rows = list((await db.execute(
            select(VehicleCustomerRelationship, Customer)
            .join(Customer, Customer.id == VehicleCustomerRelationship.customer_id)
            .where(
                VehicleCustomerRelationship.tenant_id == tenant_id,
                VehicleCustomerRelationship.vehicle_id == vehicle_id,
                VehicleCustomerRelationship.relationship_type == "default_payer",
                VehicleCustomerRelationship.effective_to.is_(None),
                VehicleCustomerRelationship.deleted_at.is_(None),
                Customer.deleted_at.is_(None),
            )
        )).all())
        if any(not customer.is_internal_fleet for _, customer in payer_rows):
            return
        for relationship, _ in payer_rows:
            relationship.effective_to = now
            relationship.is_primary = False
        await ensure_vehicle_relationship(
            db,
            tenant_id=tenant_id,
            vehicle_id=vehicle_id,
            customer_id=fleet_customer_id,
            relationship_type="default_payer",
            is_primary=True,
        )

    if existing:
        await ensure_vehicle_relationship(
            db,
            tenant_id=tenant_id,
            vehicle_id=vehicle_id,
            customer_id=fleet_customer_id,
            relationship_type="operator",
        )
        await ensure_external_default_payer()
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
    await ensure_external_default_payer()
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
        active_operator_for_customer = exists(select(VehicleCustomerRelationship.id).where(
            VehicleCustomerRelationship.vehicle_id == Vehicle.id,
            VehicleCustomerRelationship.customer_id == customer.id,
            VehicleCustomerRelationship.relationship_type == "operator",
            VehicleCustomerRelationship.effective_to.is_(None),
            VehicleCustomerRelationship.deleted_at.is_(None),
        ))
        active_other_customer_operator = exists(
            select(VehicleCustomerRelationship.id)
            .join(Customer, Customer.id == VehicleCustomerRelationship.customer_id)
            .where(
                VehicleCustomerRelationship.vehicle_id == Vehicle.id,
                VehicleCustomerRelationship.customer_id != customer.id,
                VehicleCustomerRelationship.relationship_type == "operator",
                VehicleCustomerRelationship.effective_to.is_(None),
                VehicleCustomerRelationship.deleted_at.is_(None),
                Customer.is_internal_fleet.is_(False),
                Customer.deleted_at.is_(None),
            )
        )
        owned_by_customer = or_(
            Vehicle.customer_id == customer.id,
            exists(select(VehicleCustomerRelationship.id).where(
                VehicleCustomerRelationship.vehicle_id == Vehicle.id,
                VehicleCustomerRelationship.customer_id == customer.id,
                VehicleCustomerRelationship.relationship_type == "owner",
                VehicleCustomerRelationship.effective_to.is_(None),
                VehicleCustomerRelationship.deleted_at.is_(None),
            )),
        )
        vehicle_ids = list((await db.execute(
            select(Vehicle.id).where(
                Vehicle.tenant_id == customer.tenant_id,
                Vehicle.deleted_at.is_(None),
                or_(
                    active_operator_for_customer,
                    and_(owned_by_customer, ~active_other_customer_operator),
                ),
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
