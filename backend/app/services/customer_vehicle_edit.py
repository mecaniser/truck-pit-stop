"""Shared resource and field boundaries for customer vehicle label edits."""
from uuid import UUID

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import exists, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.customer import Customer
from app.db.models.user import UserRole
from app.db.models.vehicle import Vehicle
from app.db.models.vehicle_relationship import FleetMembership, VehicleCustomerRelationship
from app.schemas.vehicle import VehicleCustomerUpdate

STAFF_VEHICLE_EDIT_ROLES = frozenset({
    UserRole.GARAGE_OWNER, UserRole.GARAGE_ADMIN, UserRole.MECHANIC,
    UserRole.RECEPTIONIST, UserRole.FLEET_MANAGER,
})


async def editable_vehicle(db: AsyncSession, actor, vehicle_id: UUID, *, customer_id: UUID | None = None, allow_linked: bool = False) -> Vehicle:
    if actor.role != UserRole.CUSTOMER and actor.role not in STAFF_VEHICLE_EDIT_ROLES:
        raise HTTPException(403, 'Insufficient permissions')
    if not actor.tenant_id or (actor.role == UserRole.CUSTOMER and (
        not actor.customer_id or (customer_id is not None and actor.customer_id != customer_id)
    )):
        raise HTTPException(403, 'Access denied')
    conditions = [Vehicle.id == vehicle_id, Vehicle.tenant_id == actor.tenant_id, Vehicle.deleted_at.is_(None)]
    account_id = customer_id if customer_id is not None else actor.customer_id if actor.role == UserRole.CUSTOMER else None
    if account_id is not None:
        account = (await db.execute(select(Customer.id).where(
            Customer.id == account_id, Customer.tenant_id == actor.tenant_id, Customer.deleted_at.is_(None),
        ))).scalar_one_or_none()
        if account is None:
            raise HTTPException(404, 'Vehicle not found')
        direct = Vehicle.customer_id == account_id
        if allow_linked:
            conditions.append(or_(direct, exists(select(VehicleCustomerRelationship.id).where(
                VehicleCustomerRelationship.vehicle_id == Vehicle.id,
                VehicleCustomerRelationship.tenant_id == actor.tenant_id,
                VehicleCustomerRelationship.customer_id == account_id,
                VehicleCustomerRelationship.relationship_type.in_(['owner', 'operator']),
                VehicleCustomerRelationship.effective_to.is_(None),
                VehicleCustomerRelationship.deleted_at.is_(None),
            ))))
        else:
            conditions.append(direct)
    vehicle = (await db.execute(select(Vehicle).where(*conditions))).scalar_one_or_none()
    if vehicle is None:
        raise HTTPException(404, 'Vehicle not found')
    if actor.role == UserRole.FLEET_MANAGER:
        membership = (await db.execute(select(FleetMembership.id).where(
            FleetMembership.vehicle_id == vehicle.id, FleetMembership.tenant_id == actor.tenant_id,
            FleetMembership.effective_to.is_(None), FleetMembership.deleted_at.is_(None),
        ))).scalar_one_or_none()
        internal = (await db.execute(select(Customer.id).where(
            Customer.id == vehicle.customer_id, Customer.tenant_id == actor.tenant_id,
            Customer.is_internal_fleet.is_(True), Customer.deleted_at.is_(None),
        ))).scalar_one_or_none()
        if membership is None and internal is None:
            raise HTTPException(403, 'Fleet managers can only manage active fleet vehicles')
    return vehicle


def customer_label_updates(data: dict) -> dict:
    try:
        return VehicleCustomerUpdate.model_validate(data).model_dump(exclude_unset=True)
    except ValidationError:
        # Do not echo submitted VINs, unknown values or foreign identifiers.
        raise HTTPException(422, {
            'code': 'invalid_customer_vehicle_update',
            'message': 'Customers may edit only unit number, license plate, color, and notes within the allowed lengths.',
        }) from None
